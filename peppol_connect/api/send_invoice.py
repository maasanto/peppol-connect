"""API endpoint for sending invoices via Peppol"""

import frappe
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist()
def send_to_peppol(sales_invoice_name):
	"""
	Send a Sales Invoice via Peppol network

	Args:
		sales_invoice_name: Name of the Sales Invoice to send

	Returns:
		dict: {"success": bool, "transmission": str, "message": str}
	"""
	# Get invoice
	invoice = frappe.get_doc("Sales Invoice", sales_invoice_name)
	invoice.check_permission("write")

	# Validate invoice is submitted
	if invoice.docstatus != 1:
		frappe.throw(_("Invoice must be submitted before sending via Peppol"))

	# Check if already sent
	existing = frappe.db.exists("Peppol Transmission", {
		"reference_doctype": "Sales Invoice",
		"reference_name": sales_invoice_name,
		"status": ["in", ["Queued", "Sending", "Sent", "Delivered"]]
	})
	if existing:
		frappe.throw(_("Invoice already queued or sent via Peppol"))

	# Get settings
	settings = frappe.get_single("E Invoice Settings")
	if not settings.get("peppol_enabled"):
		frappe.throw(_("Peppol Connect is not enabled in E Invoice Settings"))

	if not settings.get("peppol_provider"):
		frappe.throw(_("No Peppol Provider configured in E Invoice Settings"))

	try:
		# Get UBL XML from eu_einvoice (already validated)
		from peppol_connect.utils.peppol_utils import get_ubl_xml, get_peppol_ids

		ubl_xml = get_ubl_xml(invoice)
		peppol_ids = get_peppol_ids(invoice)

		# Create transmission record
		transmission = frappe.get_doc({
			"doctype": "Peppol Transmission",
			"reference_doctype": "Sales Invoice",
			"reference_name": sales_invoice_name,
			"direction": "Outbound",
			"status": "Queued",
			"provider": settings.peppol_provider,
			"recipient_peppol_id": peppol_ids["recipient_id"],
			"sender_peppol_id": peppol_ids["sender_id"],
			"document_type": "invoice",
			"ubl_xml": ubl_xml,
			"created_at": now_datetime(),
			"queued_at": now_datetime()
		})
		transmission.insert(ignore_permissions=True)
		frappe.db.commit()

		# Update invoice
		invoice.db_set("peppol_status", "Queued", update_modified=False)
		invoice.db_set("peppol_transmission_id", transmission.name, update_modified=False)

		# Queue for background sending
		frappe.enqueue(
			"peppol_connect.api.send_invoice.process_transmission",
			transmission_name=transmission.name,
			queue="default",
			timeout=300
		)

		return {
			"success": True,
			"transmission": transmission.name,
			"message": _("Invoice queued for Peppol transmission")
		}

	except Exception as e:
		frappe.log_error(f"Failed to queue invoice for Peppol: {str(e)}", "Peppol Send Error")
		frappe.throw(_("Failed to queue invoice: {0}").format(str(e)))


def process_transmission(transmission_name):
	"""
	Background job to process a single transmission

	Args:
		transmission_name: Name of Peppol Transmission record
	"""
	from peppol_connect.providers.provider_factory import get_provider_instance

	transmission = frappe.get_doc("Peppol Transmission", transmission_name)

	# Update status
	transmission.status = "Sending"
	transmission.save(ignore_permissions=True)
	frappe.db.commit()

	try:
		# Get provider
		provider = get_provider_instance(transmission.provider)

		# Send document
		result = provider.send_document(
			ubl_xml=transmission.ubl_xml,
			recipient_peppol_id=transmission.recipient_peppol_id,
			document_type=transmission.document_type
		)

		# Store API request details for debugging/audit
		import json
		if result.get("api_endpoint"):
			transmission.api_endpoint = result.get("api_endpoint")
		if result.get("request_payload"):
			# Store payload without the full XML document
			# This prevents HTML entity encoding issues and reduces duplication
			payload_for_storage = result.get("request_payload").copy()
			if "document" in payload_for_storage:
				xml_preview = payload_for_storage["document"][:200] if payload_for_storage["document"] else ""
				payload_for_storage["document"] = f"<XML content stored in ubl_xml field> (preview: {xml_preview}...)"
			transmission.request_payload = json.dumps(payload_for_storage, indent=2)

		# Update transmission
		transmission.provider_document_id = result.get("provider_document_id")
		transmission.status = "Sent"
		transmission.sent_at = now_datetime()
		transmission.error_message = None

		transmission.save(ignore_permissions=True)

		# Update invoice
		if transmission.reference_doctype and transmission.reference_name:
			frappe.db.set_value(
				transmission.reference_doctype,
				transmission.reference_name,
				{
					"peppol_status": "Sent",
					"peppol_document_id": result.get("provider_document_id"),
					"peppol_sent_date": now_datetime()
				},
				update_modified=False
			)

		frappe.db.commit()

	except Exception as e:
		# Update transmission with error
		transmission.status = "Failed"
		transmission.failed_at = now_datetime()
		transmission.error_message = str(e)
		transmission.retry_count = (transmission.retry_count or 0) + 1
		transmission.save(ignore_permissions=True)

		# Update invoice
		if transmission.reference_doctype and transmission.reference_name:
			frappe.db.set_value(
				transmission.reference_doctype,
				transmission.reference_name,
				{
					"peppol_status": "Failed",
					"peppol_error": str(e)
				},
				update_modified=False
			)

		frappe.db.commit()
		frappe.log_error(f"Failed to send Peppol transmission: {str(e)}", f"Peppol Send Error - {transmission_name}")
		raise


def auto_send_on_submit(doc, method=None):
	"""
	Hook function called on Sales Invoice submit
	Auto-sends if peppol_enabled and auto_send are both enabled

	Args:
		doc: Sales Invoice document
		method: Frappe hook method (unused)
	"""
	# Only proceed if Peppol is enabled for this invoice
	if not doc.get("peppol_enabled"):
		return

	# Check global settings
	settings = frappe.get_single("E Invoice Settings")
	if not settings.get("peppol_enabled"):
		return

	if not settings.get("peppol_auto_send"):
		return

	try:
		send_to_peppol(doc.name)
	except Exception as e:
		# Log error but don't block invoice submission
		frappe.log_error(f"Auto-send Peppol failed: {str(e)}", f"Peppol Auto-Send Error - {doc.name}")
		frappe.msgprint(_("Invoice submitted but Peppol auto-send failed: {0}").format(str(e)), indicator="orange")
