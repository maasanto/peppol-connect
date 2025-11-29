"""Webhook endpoints for Peppol providers"""

import frappe
from frappe import _
from frappe.utils import now_datetime
import json


@frappe.whitelist(allow_guest=True)
def recommand_webhook():
	"""
	Webhook endpoint for Recommand.eu status updates
	Called by Recommand when document status changes

	Returns:
		dict: {"status": "ok"} or {"status": "error", "message": str}
	"""
	try:
		# Get webhook data
		data = frappe.request.json

		if not data:
			frappe.log_error("Empty webhook data received", "Peppol Webhook Error")
			return {"status": "error", "message": "No data received"}

		# Extract document ID
		document_id = data.get("documentId") or data.get("id")
		if not document_id:
			frappe.log_error(f"Missing documentId in webhook: {json.dumps(data)}", "Peppol Webhook Error")
			return {"status": "error", "message": "Missing documentId"}

		# Find transmission
		transmissions = frappe.get_all(
			"Peppol Transmission",
			filters={"provider_document_id": document_id},
			fields=["name"],
			limit=1
		)

		if not transmissions:
			frappe.log_error(
				f"Transmission not found for document_id: {document_id}\nData: {json.dumps(data)}",
				"Peppol Webhook - Unknown Document"
			)
			return {"status": "error", "message": "Document not found"}

		# Update transmission
		transmission = frappe.get_doc("Peppol Transmission", transmissions[0].name)

		# Map provider status to our status
		provider_status = data.get("status", "").lower()
		status_map = {
			"queued": "Queued",
			"processing": "Sending",
			"sent": "Sent",
			"delivered": "Delivered",
			"failed": "Failed"
		}
		new_status = status_map.get(provider_status, transmission.status)

		# Update transmission
		transmission.status = new_status
		transmission.webhook_data = json.dumps(data, indent=2)
		transmission.last_status_check = now_datetime()

		if new_status == "Delivered":
			transmission.delivered_at = now_datetime()
		elif new_status == "Failed":
			transmission.failed_at = now_datetime()
			error_info = data.get("error", {})
			if isinstance(error_info, dict):
				transmission.error_message = error_info.get("message", "Delivery failed")
			else:
				transmission.error_message = str(error_info) if error_info else "Delivery failed"

		transmission.save(ignore_permissions=True)

		# Update reference document
		if transmission.reference_doctype and transmission.reference_name:
			update_data = {"peppol_status": new_status}

			if new_status == "Delivered":
				update_data["peppol_delivered_date"] = now_datetime()
			elif new_status == "Failed":
				update_data["peppol_error"] = transmission.error_message

			frappe.db.set_value(
				transmission.reference_doctype,
				transmission.reference_name,
				update_data,
				update_modified=False
			)

		frappe.db.commit()

		return {"status": "ok"}

	except Exception as e:
		frappe.log_error(f"Webhook processing failed: {str(e)}", "Peppol Webhook Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def generic_webhook():
	"""
	Generic webhook endpoint for other providers
	Can be extended for different provider formats

	Returns:
		dict: {"status": "ok"} or {"status": "error", "message": str}
	"""
	try:
		data = frappe.request.json

		# Log for debugging
		frappe.log_error(
			f"Generic webhook received:\n{json.dumps(data, indent=2)}",
			"Peppol Webhook - Generic"
		)

		# TODO: Implement generic webhook handling
		return {"status": "ok", "message": "Logged for processing"}

	except Exception as e:
		frappe.log_error(f"Generic webhook error: {str(e)}", "Peppol Webhook Error")
		return {"status": "error", "message": str(e)}
