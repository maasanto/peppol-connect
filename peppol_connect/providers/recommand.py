"""Recommand Peppol Provider Implementation"""

import frappe
import requests
from requests.auth import HTTPBasicAuth
import json


class RecommandProvider:
	"""
	Peppol provider implementation for Recommand
	Documentation: https://recommand.eu/fr-FR/docs
	"""

	def __init__(self, provider_doc):
		"""
		Initialize Recommand provider

		Args:
			provider_doc: Peppol Provider document
		"""
		self.provider = provider_doc
		self.api_key = provider_doc.get_password("api_key")
		self.api_secret = provider_doc.get_password("api_secret")
		self.team_id = provider_doc.team_id
		self.company_id = provider_doc.company_id
		self.use_playground = provider_doc.use_playground

	def get_base_url(self):
		"""Get base URL based on environment (production or playground)"""
		if self.use_playground and self.provider.api_playground_url:
			return self.provider.api_playground_url
		return self.provider.api_base_url

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
			Response JSON or raises exception
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

			# Log request for debugging
			frappe.log_error(
				title=f"Recommand API {method} {endpoint}",
				message=f"Status: {response.status_code}\nURL: {url}\nResponse: {response.text[:500]}"
			)

			response.raise_for_status()

			return response.json() if response.text else {}

		except requests.exceptions.RequestException as e:
			error_msg = f"Recommand API Error: {str(e)}"
			if hasattr(e, 'response') and e.response is not None:
				error_msg += f"\nResponse: {e.response.text}"

			frappe.log_error(
				title=f"Recommand API Error - {method} {endpoint}",
				message=error_msg
			)
			raise

	def test_connection(self):
		"""
		Test API connection and authentication

		Returns:
			dict with 'success' (bool) and 'message' (str)
		"""
		try:
			# Try to get team info or similar endpoint
			response = self._make_request("GET", f"/{self.team_id}/companies")

			return {
				"success": True,
				"message": "Connection successful"
			}

		except Exception as e:
			return {
				"success": False,
				"message": f"Connection failed: {str(e)}"
			}

	def send_document(self, document, recipient_peppol_id, document_type="invoice"):
		"""
		Send a document via Peppol network

		Args:
			document: Document data in Recommand JSON format
			recipient_peppol_id: Peppol ID of recipient (format: "scheme:id")
			document_type: Type of document (default: "invoice")

		Returns:
			dict with provider document ID and status
		"""
		if not self.company_id:
			raise ValueError("Company ID is required for sending documents")

		endpoint = f"/{self.company_id}/sendDocument"

		payload = {
			"recipient": recipient_peppol_id,
			"documentType": document_type,
			"document": document
		}

		response = self._make_request("POST", endpoint, data=payload)

		return {
			"provider_document_id": response.get("documentId") or response.get("id"),
			"status": response.get("status", "sent"),
			"response": response
		}

	def get_document_status(self, document_id):
		"""
		Get delivery status of a sent document

		Args:
			document_id: Provider's document identifier

		Returns:
			dict with current status and delivery information
		"""
		if not self.team_id:
			raise ValueError("Team ID is required for checking document status")

		endpoint = f"/{self.team_id}/documents/{document_id}"

		response = self._make_request("GET", endpoint)

		# Map Recommand status to our status
		recommand_status = response.get("status", "unknown").lower()

		status_mapping = {
			"sent": "Sent",
			"delivered": "Delivered",
			"failed": "Failed",
			"pending": "Sending"
		}

		our_status = status_mapping.get(recommand_status, "Sent")

		return {
			"status": our_status,
			"provider_status": recommand_status,
			"details": response
		}

	def verify_participant(self, peppol_id):
		"""
		Verify that a Peppol participant ID exists and can receive documents

		Args:
			peppol_id: Peppol ID to verify (format: "scheme:id")

		Returns:
			dict with 'valid' (bool) and participant details
		"""
		endpoint = "/verify"

		payload = {
			"peppolAddress": peppol_id
		}

		try:
			response = self._make_request("POST", endpoint, data=payload)

			return {
				"valid": response.get("valid", False),
				"participant_id": peppol_id,
				"details": response
			}

		except Exception as e:
			return {
				"valid": False,
				"participant_id": peppol_id,
				"error": str(e)
			}

	def register_company(self, company_data):
		"""
		Register a company with Recommand

		Args:
			company_data: Dictionary containing company information
				- name: Company name
				- vat_number: VAT/Tax ID
				- peppol_id: Peppol participant ID (format: "scheme:id")
				- address: Address details

		Returns:
			dict with registration details including provider company ID
		"""
		if not self.team_id:
			raise ValueError("Team ID is required for registering companies")

		endpoint = f"/{self.team_id}/companies"

		# Map our data to Recommand format
		payload = {
			"name": company_data.get("name"),
			"vatNumber": company_data.get("vat_number"),
			"peppolId": company_data.get("peppol_id"),
			"address": company_data.get("address", {})
		}

		response = self._make_request("POST", endpoint, data=payload)

		return {
			"provider_company_id": response.get("id") or response.get("companyId"),
			"registration_details": response
		}


def get_provider_instance(provider_name=None):
	"""
	Get a Recommand provider instance

	Args:
		provider_name: Name of the Peppol Provider (optional, uses default from settings)

	Returns:
		RecommandProvider instance
	"""
	if not provider_name:
		settings = frappe.get_single("Peppol Settings")
		if not settings.enabled:
			frappe.throw("Peppol Connect is not enabled")
		provider_name = settings.provider

	if not provider_name:
		frappe.throw("No Peppol Provider configured in Peppol Settings")

	provider_doc = frappe.get_doc("Peppol Provider", provider_name)

	if not provider_doc.enabled:
		frappe.throw(f"Peppol Provider '{provider_name}' is not enabled")

	if provider_doc.provider_code != "recommand":
		frappe.throw(f"Provider '{provider_name}' is not a Recommand provider")

	return RecommandProvider(provider_doc)
