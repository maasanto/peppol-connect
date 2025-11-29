"""Utility functions for Peppol Connect"""

import frappe
from frappe import _


def get_ubl_xml(invoice):
	"""
	Get UBL XML from Sales Invoice using eu_einvoice app

	The eu_einvoice app is responsible for generating and validating
	the UBL XML. We simply call its method and trust the output.

	Args:
		invoice: Sales Invoice document or name

	Returns:
		str: UBL XML string

	Raises:
		frappe.ValidationError: If UBL generation fails
	"""
	from eu_einvoice.european_e_invoice.custom.sales_invoice import get_einvoice

	if isinstance(invoice, str):
		invoice_name = invoice
	else:
		invoice_name = invoice.name

	try:
		# get_einvoice returns bytes
		xml_bytes = get_einvoice(invoice_name)

		# Decode to string
		ubl_xml = xml_bytes.decode('utf-8')

		return ubl_xml

	except Exception as e:
		frappe.throw(
			_("Failed to generate UBL XML for invoice {0}: {1}").format(
				invoice_name, str(e)
			)
		)


def get_peppol_ids(invoice):
	"""
	Get Peppol participant IDs from invoice

	Args:
		invoice: Sales Invoice document or name

	Returns:
		dict: {
			"sender_id": "scheme:id",
			"recipient_id": "scheme:id"
		}

	Raises:
		frappe.ValidationError: If Peppol IDs are missing
	"""
	if isinstance(invoice, str):
		invoice = frappe.get_doc("Sales Invoice", invoice)

	# Get sender ID from Company
	company = frappe.get_doc("Company", invoice.company)

	if not company.get("eas") or not company.get("tax_id"):
		frappe.throw(
			_("Company {0} is missing EAS (Endpoint Scheme) or Tax ID").format(company.name)
		)

	sender_id = f"{company.eas}:{company.tax_id}"

	# Get recipient ID from Customer
	customer = frappe.get_doc("Customer", invoice.customer)

	if not customer.get("eas") or not customer.get("tax_id"):
		frappe.throw(
			_("Customer {0} is missing EAS (Endpoint Scheme) or Tax ID").format(customer.name)
		)

	recipient_id = f"{customer.eas}:{customer.tax_id}"

	return {
		"sender_id": sender_id,
		"recipient_id": recipient_id
	}


def validate_peppol_id(peppol_id):
	"""
	Validate Peppol ID format

	Args:
		peppol_id: String in format "scheme:identifier"

	Returns:
		dict: {
			"valid": bool,
			"scheme": str,
			"identifier": str,
			"error": str (if invalid)
		}
	"""
	if not peppol_id:
		return {"valid": False, "error": "Peppol ID is required"}

	if ":" not in peppol_id:
		return {
			"valid": False,
			"error": "Invalid format. Expected 'scheme:identifier' (e.g., '0208:0123456789')"
		}

	parts = peppol_id.split(":", 1)
	if len(parts) != 2:
		return {"valid": False, "error": "Invalid format. Expected 'scheme:identifier'"}

	scheme, identifier = parts

	if not scheme or not identifier:
		return {"valid": False, "error": "Both scheme and identifier are required"}

	return {
		"valid": True,
		"scheme": scheme,
		"identifier": identifier
	}
