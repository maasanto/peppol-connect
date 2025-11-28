"""Validation utilities for Peppol Connect"""

import frappe
import re


def validate_peppol_id(peppol_id):
	"""
	Validate Peppol ID format (scheme:identifier)

	Args:
		peppol_id: String in format "scheme:id" (e.g., "0208:0123456789")

	Returns:
		dict with 'valid' (bool), 'scheme' (str), 'identifier' (str), 'error' (str)
	"""
	if not peppol_id:
		return {"valid": False, "error": "Peppol ID is required"}

	# Format should be scheme:identifier
	if ":" not in peppol_id:
		return {"valid": False, "error": "Invalid format. Expected 'scheme:identifier' (e.g., '0208:0123456789')"}

	parts = peppol_id.split(":", 1)
	if len(parts) != 2:
		return {"valid": False, "error": "Invalid format. Expected 'scheme:identifier'"}

	scheme, identifier = parts

	# Validate scheme (should be numeric, typically 4 digits)
	if not scheme or not identifier:
		return {"valid": False, "error": "Both scheme and identifier are required"}

	# Common Peppol schemes
	valid_schemes = ["0208", "0007", "9925", "9956", "0088", "0184", "9902", "9908"]

	if scheme not in valid_schemes:
		frappe.log_error(
			f"Unknown Peppol scheme: {scheme}. Proceeding anyway.",
			"Peppol Validation Warning"
		)

	return {
		"valid": True,
		"scheme": scheme,
		"identifier": identifier
	}


def get_peppol_id_from_customer(customer_name):
	"""
	Get formatted Peppol ID from Customer

	Args:
		customer_name: Customer name

	Returns:
		String in format "scheme:id" or None
	"""
	customer = frappe.get_doc("Customer", customer_name)

	if not customer.get("peppol_enabled"):
		return None

	scheme = customer.get("peppol_scheme")
	participant_id = customer.get("peppol_participant_id")

	if not scheme or not participant_id:
		return None

	return f"{scheme}:{participant_id}"


def get_peppol_id_from_company(company_name):
	"""
	Get formatted Peppol ID from Company

	Args:
		company_name: Company name

	Returns:
		String in format "scheme:id" or None
	"""
	company = frappe.get_doc("Company", company_name)

	if not company.get("peppol_enabled"):
		return None

	scheme = company.get("peppol_scheme")
	participant_id = company.get("peppol_participant_id")

	if not scheme or not participant_id:
		return None

	return f"{scheme}:{participant_id}"


def validate_peppol_settings():
	"""
	Validate that Peppol Settings are properly configured

	Returns:
		dict with 'valid' (bool) and 'error' (str)
	"""
	settings = frappe.get_single("Peppol Settings")

	if not settings.enabled:
		return {"valid": False, "error": "Peppol Connect is not enabled"}

	if not settings.provider:
		return {"valid": False, "error": "No Peppol Provider configured"}

	# Check provider
	try:
		provider = frappe.get_doc("Peppol Provider", settings.provider)

		if not provider.enabled:
			return {"valid": False, "error": f"Provider '{settings.provider}' is not enabled"}

		# Check required credentials
		if not provider.api_key:
			return {"valid": False, "error": "Provider API Key is missing"}

		if not provider.api_secret:
			return {"valid": False, "error": "Provider API Secret is missing"}

	except frappe.DoesNotExistError:
		return {"valid": False, "error": f"Provider '{settings.provider}' does not exist"}

	return {"valid": True}
