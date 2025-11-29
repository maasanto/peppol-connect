"""Utility functions for Peppol Connect"""

import frappe
from frappe import _

def get_peppol_address(doc):
	"""
	Get Peppol participant ID for a Company or Customer

	This utility returns the full Peppol address by concatenating the EAS common code
	and the electronic address, for example: 0208:0888888895

	Args:
		doc: Company or Customer document, or document name (str)

	Returns:
		str: Peppol ID in format "scheme_code:electronic_address" (e.g., "0208:0888888895")
		     Returns None if fields are not set

	Raises:
		frappe.ValidationError: If required fields are missing

	Examples:
		# Pass a document object
		company = frappe.get_doc("Company", "My Company")
		peppol_id = get_peppol_address(company)

		# Pass a document name - will auto-detect if it's a Company or Customer
		peppol_id = get_peppol_address("My Company")
		peppol_id = get_peppol_address("Customer Name")
	"""
	# If doc is a string, try to find it in Company or Customer
	if isinstance(doc, str):
		docname = doc
		# Try Company first
		if frappe.db.exists("Company", docname):
			doc = frappe.get_doc("Company", docname)
		# Try Customer
		elif frappe.db.exists("Customer", docname):
			doc = frappe.get_doc("Customer", docname)
		else:
			frappe.throw(_("Document {0} not found in Company or Customer").format(docname))

	if not doc.get("electronic_address_scheme") or not doc.get("electronic_address"):
		return None

	# Get the common code value from the EAS link field
	scheme_code = frappe.db.get_value("Common Code", doc.electronic_address_scheme, "common_code")

	if not scheme_code:
		frappe.throw(
			_("{0} {1} has an invalid EAS (Endpoint Scheme). The Common Code could not be found.").format(
				doc.doctype, doc.name
			)
		)

	return f"{scheme_code}:{doc.electronic_address}"


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

	# Get sender ID from Company using the new utility
	sender_id = get_peppol_address(invoice.company)
	if not sender_id:
		frappe.throw(
			_("Company {0} is missing EAS (Endpoint Scheme) or Electronic Address").format(invoice.company)
		)

	# Get recipient ID from Customer using the new utility
	recipient_id = get_peppol_address(invoice.customer)
	if not recipient_id:
		frappe.throw(
			_("Customer {0} is missing EAS (Endpoint Scheme) or Electronic Address").format(invoice.customer)
		)

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
