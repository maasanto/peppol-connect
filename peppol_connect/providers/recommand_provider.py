"""Recommand.eu Peppol Access Point provider implementation"""

import frappe
import requests
from requests.auth import HTTPBasicAuth
import xml.etree.ElementTree as ET
from peppol_connect.providers.base_provider import BasePeppolProvider
from eu_einvoice.peppol import PEPPOL_CUSTOMIZATION_ID


class RecommandProvider(BasePeppolProvider):
	"""
	Peppol provider implementation for Recommand.eu

	Documentation: https://recommand.eu/en/docs
	API: https://peppol.recommand.eu/api/v1
	"""

	def __init__(self, provider_settings):
		"""Initialize Recommand provider"""
		super().__init__(provider_settings)
		self.team_id = provider_settings.team_id
		self.company_id = provider_settings.company_id

	def get_base_url(self):
		"""Get base URL based on environment"""
		if self.test_mode and self.settings.api_playground_url:
			return self.settings.api_playground_url
		return self.api_base_url

	def _extract_doctype_id(self, ubl_xml):
		"""
		Build the Peppol document type ID from UBL XML root element

		The doctypeId format is: {namespace}::{root_element}##{PEPPOL_CUSTOMIZATION_ID}::2.1

		Args:
			ubl_xml: UBL XML string

		Returns:
			str: Document type ID
		"""
		try:
			root = ET.fromstring(ubl_xml)
			# Extract namespace and root element name
			root_element = root.tag.split('}')[-1]  # e.g., "Invoice" or "CreditNote"
			namespace = root.tag.split('}')[0].strip('{')  # e.g., "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"

			# Construct the doctypeId using the constant from eu_einvoice
			# Format: namespace::root_element##customization_id::ubl_version
			doctype_id = f"{namespace}::{root_element}##{PEPPOL_CUSTOMIZATION_ID}::2.1"
			return doctype_id

		except Exception as e:
			frappe.logger().error(f"Error extracting doctypeId from UBL XML: {str(e)}")
			# Return default invoice doctypeId as fallback
			return f"urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice##{PEPPOL_CUSTOMIZATION_ID}::2.1"

	def _get_auth(self):
		"""Get HTTP Basic Auth"""
		return HTTPBasicAuth(self.api_key, self.api_secret)

	def _make_request(self, method, endpoint, data=None, params=None):
		"""
		Make HTTP request to Recommand API

		Args:
			method: HTTP method (GET, POST, etc.)
			endpoint: API endpoint path
			data: Request body (will be JSON encoded)
			params: Query parameters

		Returns:
			dict: Response JSON

		Raises:
			Exception: If request fails
		"""
		url = f"{self.get_base_url()}{endpoint}"

		headers = {
			"Content-Type": "application/json",
			"Accept": "application/json"
		}

		try:
			response = requests.request(
				method=method,
				url=url,
				auth=self._get_auth(),
				headers=headers,
				json=data,
				params=params,
				timeout=30
			)

			# Log for debugging
			frappe.logger().debug(
				f"Recommand API {method} {endpoint}: {response.status_code}"
			)

			response.raise_for_status()

			# Try to parse JSON response
			if response.text:
				try:
					return response.json()
				except ValueError as json_error:
					frappe.logger().warning(f"Failed to parse JSON from {endpoint}: {json_error}")
					frappe.logger().warning(f"Response text: {response.text[:200]}")
					return {}
			else:
				return {}

		except requests.exceptions.RequestException as e:
			error_msg = f"Recommand API Error: {str(e)}"
			if hasattr(e, 'response') and e.response is not None:
				error_msg += f"\nResponse: {e.response.text}"

			frappe.log_error(
				error_msg,
				f"Recommand API Error - {method} {endpoint}"
			)
			raise Exception(error_msg)

	def send_document(self, ubl_xml, recipient_peppol_id, document_type="invoice"):
		"""
		Send UBL XML document via Peppol network

		Args:
			ubl_xml: UBL XML string
			recipient_peppol_id: Recipient's Peppol ID (format: "scheme:id")
			document_type: Document type (default: "invoice")

		Returns:
			dict: {
				"provider_document_id": str,
				"status": str,
				"response": dict,
				"api_endpoint": str,
				"request_payload": dict
			}
		"""
		if not self.company_id:
			raise ValueError("Company ID is required for sending documents")

		# Recommand API endpoint
		endpoint = f"/{self.company_id}/sendDocument"
		full_url = f"{self.get_base_url()}{endpoint}"

		# Extract doctypeId from UBL XML CustomizationID
		doctype_id = self._extract_doctype_id(ubl_xml)

		payload = {
			"recipient": recipient_peppol_id,
			"documentType": "xml",
			"doctypeId": doctype_id,
			"document": ubl_xml,
		}

		response = self._make_request("POST", endpoint, data=payload)

		return {
			"provider_document_id": response.get("documentId") or response.get("id"),
			"status": "Sent",
			"response": response,
			"api_endpoint": full_url,
			"request_payload": payload
		}

	def get_document_status(self, document_id):
		"""
		Get delivery status of a sent document

		Args:
			document_id: Provider's document identifier

		Returns:
			dict: {
				"status": str,
				"provider_status": str,
				"error": str,
				"details": dict
			}
		"""
		if not self.team_id:
			raise ValueError("Team ID is required for checking document status")

		endpoint = f"/{self.team_id}/documents/{document_id}"
		response = self._make_request("GET", endpoint)

		provider_status = response.get("status", "unknown")
		normalized_status = self.normalize_status(provider_status)

		result = {
			"status": normalized_status,
			"provider_status": provider_status,
			"details": response
		}

		# Add error if failed
		if normalized_status == "Failed":
			error_info = response.get("error", {})
			if isinstance(error_info, dict):
				result["error"] = error_info.get("message", "Unknown error")
			else:
				result["error"] = str(error_info) if error_info else "Unknown error"

		return result

	def test_connection(self):
		"""
		Test API connection and authentication

		Returns:
			dict: {"success": bool, "message": str}
		"""
		try:
			# Try to get company info
			if self.team_id:
				response = self._make_request("GET", f"/{self.team_id}/companies")
				return {
					"success": True,
					"message": "Connection successful"
				}
			else:
				return {
					"success": False,
					"message": "Team ID not configured"
				}

		except Exception as e:
			return {
				"success": False,
				"message": f"Connection failed: {str(e)}"
			}

	def verify_recipient(self, peppol_id):
		"""
		Verify if a recipient is reachable on the Peppol network

		Args:
			peppol_id: Recipient's Peppol ID (format: "scheme:id", e.g., "0208:0888888895")

		Returns:
			dict: {
				"reachable": bool,
				"participant_id": str,
				"details": dict
			}
		"""
		if not self.company_id:
			raise ValueError("Company ID is required for verifying recipients")

		# URL encode the peppol_id (replace : with %3A)
		import urllib.parse
		encoded_peppol_id = urllib.parse.quote(peppol_id, safe='')

		# Recommand API endpoint for participant verification
		endpoint = f"/{self.company_id}/participants/{encoded_peppol_id}"

		# Make direct request to get better error handling
		url = f"{self.get_base_url()}{endpoint}"
		headers = {
			"Accept": "application/json"
		}

		try:
			import requests
			response = requests.get(
				url,
				auth=self._get_auth(),
				headers=headers,
				timeout=30
			)

			# Log the response for debugging
			frappe.logger().info(f"Peppol verification for {peppol_id}: Status {response.status_code}")
			frappe.logger().info(f"Response body: {response.text[:500] if response.text else 'empty'}")

			# 200 = participant found and reachable
			if response.status_code == 200:
				try:
					details = response.json() if response.text else {}
				except (ValueError, TypeError):
					details = {"raw_response": response.text[:200] if response.text else ""}

				return {
					"reachable": True,
					"participant_id": peppol_id,
					"details": details
				}

			# 404 = participant not found
			elif response.status_code == 404:
				return {
					"reachable": False,
					"participant_id": peppol_id,
					"details": {"error": "Participant not found in Peppol network"}
				}

			# Other status codes
			else:
				response.raise_for_status()  # Will raise an exception
				return {
					"reachable": False,
					"participant_id": peppol_id,
					"details": {"error": f"Unexpected status code: {response.status_code}"}
				}

		except requests.exceptions.RequestException as e:
			error_msg = str(e)
			frappe.log_error(
				f"Error verifying Peppol recipient {peppol_id}: {error_msg}",
				"Peppol Recipient Verification Error"
			)
			# Return as unreachable rather than throwing
			return {
				"reachable": False,
				"participant_id": peppol_id,
				"details": {"error": error_msg}
			}

	def verify_document_support(self, peppol_id, document_type_id):
		"""
		Verify if a recipient supports a specific document type

		Args:
			peppol_id: Recipient's Peppol ID (format: "scheme:id")
			document_type_id: Peppol document type identifier

		Returns:
			dict: {
				"supported": bool,
				"participant_id": str,
				"document_type_id": str,
				"details": dict
			}
		"""
		if not self.company_id:
			raise ValueError("Company ID is required for verifying document support")

		# URL encode both peppol_id and document_type_id
		import urllib.parse
		encoded_peppol_id = urllib.parse.quote(peppol_id, safe='')
		encoded_doctype_id = urllib.parse.quote(document_type_id, safe='')

		# Recommand API endpoint for document type verification
		endpoint = f"/{self.company_id}/participants/{encoded_peppol_id}/documentTypes/{encoded_doctype_id}"

		# Make direct request to get better error handling
		url = f"{self.get_base_url()}{endpoint}"
		headers = {
			"Accept": "application/json"
		}

		try:
			import requests
			response = requests.get(
				url,
				auth=self._get_auth(),
				headers=headers,
				timeout=30
			)

			# Log the response for debugging
			frappe.logger().info(f"Document support verification for {peppol_id}, doctype {document_type_id}: Status {response.status_code}")
			frappe.logger().info(f"Response body: {response.text[:500] if response.text else 'empty'}")

			# 200 = document type is supported
			if response.status_code == 200:
				try:
					details = response.json() if response.text else {}
				except (ValueError, TypeError):
					details = {"raw_response": response.text[:200] if response.text else ""}

				return {
					"supported": True,
					"participant_id": peppol_id,
					"document_type_id": document_type_id,
					"details": details
				}

			# 404 = document type not supported or participant not found
			elif response.status_code == 404:
				return {
					"supported": False,
					"participant_id": peppol_id,
					"document_type_id": document_type_id,
					"details": {"error": "Document type not supported by this participant"}
				}

			# Other status codes
			else:
				response.raise_for_status()  # Will raise an exception
				return {
					"supported": False,
					"participant_id": peppol_id,
					"document_type_id": document_type_id,
					"details": {"error": f"Unexpected status code: {response.status_code}"}
				}

		except requests.exceptions.RequestException as e:
			error_msg = str(e)
			frappe.log_error(
				f"Error verifying document support for {peppol_id}: {error_msg}",
				"Peppol Document Support Verification Error"
			)
			# Return as not supported rather than throwing
			return {
				"supported": False,
				"participant_id": peppol_id,
				"document_type_id": document_type_id,
				"details": {"error": error_msg}
			}
