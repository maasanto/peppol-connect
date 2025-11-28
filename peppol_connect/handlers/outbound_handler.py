"""Handler for outbound Peppol documents (Sales Invoice)"""

import frappe
from frappe.utils import now_datetime
from peppol_connect.utils.validation import (
	get_peppol_id_from_customer,
	validate_peppol_settings
)
from peppol_connect.converters.outbound import convert_sales_invoice_to_recommand
import json


def validate_peppol_fields(doc, method=None):
	"""
	Validate Peppol fields before saving Sales Invoice

	Args:
		doc: Sales Invoice document
		method: Frappe method (unused)
	"""
	if not doc.get("peppol_enabled"):
		return

	# Check if Peppol is enabled globally
	settings = frappe.get_single("Peppol Settings")
	if not settings.enabled:
		frappe.throw("Peppol Connect is not enabled. Please configure Peppol Settings first.")

	# Check if customer has Peppol enabled
	customer = frappe.get_doc("Customer", doc.customer)
	if not customer.get("peppol_enabled"):
		frappe.throw(f"Customer '{doc.customer}' is not enabled for Peppol. Please configure customer's Peppol settings.")

	# Validate customer Peppol ID
	recipient_id = get_peppol_id_from_customer(doc.customer)
	if not recipient_id:
		frappe.throw(f"Customer '{doc.customer}' does not have a valid Peppol ID configured.")

	# Check if company has Peppol enabled
	company = frappe.get_doc("Company", doc.company)
	if not company.get("peppol_enabled"):
		frappe.throw(f"Company '{doc.company}' is not enabled for Peppol. Please configure company's Peppol settings.")


def on_invoice_submit(doc, method=None):
	"""
	Queue invoice for Peppol sending when submitted

	Args:
		doc: Sales Invoice document
		method: Frappe method (unused)
	"""
	# Only proceed if Peppol is enabled for this invoice
	if not doc.get("peppol_enabled"):
		return

	# Validate settings
	validation_result = validate_peppol_settings()
	if not validation_result.get("valid"):
		frappe.log_error(
			f"Cannot queue Peppol document: {validation_result.get('error')}",
			"Peppol Queue Error"
		)
		# Update invoice status
		doc.db_set("peppol_status", "Failed", update_modified=False)
		doc.db_set("peppol_error", validation_result.get("error"), update_modified=False)
		return

	# Get recipient Peppol ID
	recipient_id = get_peppol_id_from_customer(doc.customer)
	if not recipient_id:
		error_msg = f"Customer '{doc.customer}' does not have a valid Peppol ID"
		frappe.log_error(error_msg, "Peppol Queue Error")
		doc.db_set("peppol_status", "Failed", update_modified=False)
		doc.db_set("peppol_error", error_msg, update_modified=False)
		return

	try:
		# Convert invoice to Recommand JSON
		peppol_json = convert_sales_invoice_to_recommand(doc.name)

		# Get provider from settings
		settings = frappe.get_single("Peppol Settings")
		provider = settings.provider

		# Create queue entry
		queue_doc = frappe.get_doc({
			"doctype": "Peppol Document Queue",
			"reference_doctype": "Sales Invoice",
			"reference_name": doc.name,
			"direction": "Outbound",
			"status": "Queued",
			"provider": provider,
			"recipient_peppol_id": recipient_id,
			"document_type": "invoice",
			"peppol_json": json.dumps(peppol_json, indent=2),
			"created_at": now_datetime(),
			"queued_at": now_datetime()
		})
		queue_doc.insert(ignore_permissions=True)

		# Update invoice
		doc.db_set("peppol_status", "Queued", update_modified=False)
		doc.db_set("peppol_queue_link", queue_doc.name, update_modified=False)
		doc.db_set("peppol_error", None, update_modified=False)

		frappe.msgprint(f"Invoice queued for Peppol sending (Queue ID: {queue_doc.name})")

	except Exception as e:
		error_msg = f"Failed to queue invoice: {str(e)}"
		frappe.log_error(error_msg, "Peppol Queue Error")
		doc.db_set("peppol_status", "Failed", update_modified=False)
		doc.db_set("peppol_error", error_msg, update_modified=False)
		frappe.throw(error_msg)


def on_invoice_cancel(doc, method=None):
	"""
	Handle invoice cancellation

	Args:
		doc: Sales Invoice document
		method: Frappe method (unused)
	"""
	if not doc.get("peppol_queue_link"):
		return

	try:
		# Cancel the queue entry if it hasn't been sent yet
		queue_doc = frappe.get_doc("Peppol Document Queue", doc.peppol_queue_link)

		if queue_doc.status in ["Queued", "Failed"]:
			queue_doc.status = "Cancelled"
			queue_doc.save(ignore_permissions=True)

			doc.db_set("peppol_status", "Not Sent", update_modified=False)

	except Exception as e:
		frappe.log_error(f"Error cancelling Peppol queue entry: {str(e)}", "Peppol Handler")
