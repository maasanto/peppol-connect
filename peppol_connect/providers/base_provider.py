"""Base class for Peppol Access Point providers"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class BasePeppolProvider(ABC):
	"""
	Abstract base class for Peppol Access Point providers

	All provider implementations must inherit from this class and
	implement all abstract methods.
	"""

	def __init__(self, provider_settings):
		"""
		Initialize provider with settings

		Args:
			provider_settings: Peppol Provider Settings document
		"""
		self.settings = provider_settings
		self.api_key = provider_settings.get_password("api_key")
		self.api_secret = provider_settings.get_password("api_secret")
		self.api_base_url = provider_settings.api_base_url
		self.test_mode = provider_settings.use_playground

	@abstractmethod
	def send_document(
		self,
		ubl_xml: str,
		recipient_peppol_id: str,
		document_type: str = "invoice"
	) -> Dict:
		"""
		Send UBL XML document through Peppol network

		Args:
			ubl_xml: UBL XML string (already validated)
			recipient_peppol_id: Recipient's Peppol ID (format: "scheme:id")
			document_type: Type of document (default: "invoice")

		Returns:
			dict: {
				"provider_document_id": str,
				"status": str,
				"response": dict
			}

		Raises:
			Exception: If sending fails
		"""
		pass

	@abstractmethod
	def get_document_status(self, document_id: str) -> Dict:
		"""
		Check delivery status of a sent document

		Args:
			document_id: Provider's document identifier

		Returns:
			dict: {
				"status": str (Queued|Sending|Sent|Delivered|Failed),
				"provider_status": str,
				"error": str (if failed),
				"details": dict
			}

		Raises:
			Exception: If status check fails
		"""
		pass

	@abstractmethod
	def test_connection(self) -> Dict:
		"""
		Test API connection and credentials

		Returns:
			dict: {
				"success": bool,
				"message": str
			}
		"""
		pass

	@abstractmethod
	def verify_recipient(self, peppol_id: str) -> Dict:
		"""
		Verify if a recipient is reachable on the Peppol network

		Args:
			peppol_id: Recipient's Peppol ID (format: "scheme:id")

		Returns:
			dict: {
				"reachable": bool,
				"participant_id": str,
				"details": dict (optional provider-specific details)
			}

		Raises:
			Exception: If verification fails
		"""
		pass

	@abstractmethod
	def verify_document_support(self, peppol_id: str, document_type_id: str) -> Dict:
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
				"details": dict (optional provider-specific details)
			}

		Raises:
			Exception: If verification fails
		"""
		pass

	def normalize_status(self, provider_status: str) -> str:
		"""
		Normalize provider-specific status to standard status

		Args:
			provider_status: Provider's status string

		Returns:
			str: Normalized status (Queued|Sending|Sent|Delivered|Failed)
		"""
		# Default implementation - override in subclass if needed
		status_lower = provider_status.lower()

		if status_lower in ["queued", "pending"]:
			return "Queued"
		elif status_lower in ["processing", "sending"]:
			return "Sending"
		elif status_lower in ["sent", "transmitted"]:
			return "Sent"
		elif status_lower in ["delivered", "acknowledged"]:
			return "Delivered"
		elif status_lower in ["failed", "error", "rejected"]:
			return "Failed"
		else:
			return provider_status
