"""Recommand.eu Peppol Access Point provider implementation"""

import frappe
import requests
from requests.auth import HTTPBasicAuth
import base64

from peppol_connect.providers.base_provider import BasePeppolProvider


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
			return response.json() if response.text else {}

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
				"response": dict
			}
		"""
		if not self.company_id:
			raise ValueError("Company ID is required for sending documents")

		# Base64 encode the UBL XML
		ubl_base64 = base64.b64encode(ubl_xml.encode('utf-8')).decode('utf-8')

		# Recommand API endpoint
		endpoint = f"/{self.company_id}/documents"

		payload = {
			"recipient": recipient_peppol_id,
			"documentType": document_type,
			"document": ubl_base64,
			"format": "UBL"
		}

		response = self._make_request("POST", endpoint, data=payload)

		return {
			"provider_document_id": response.get("documentId") or response.get("id"),
			"status": "Sent",
			"response": response
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
