"""Background task to check status of sent Peppol documents"""

import frappe
from frappe.utils import now_datetime
from peppol_connect.providers import get_provider_instance


def check_document_statuses():
	"""
	Check delivery status of sent documents
	This function is called by the scheduler
	"""
	settings = frappe.get_single("Peppol Settings")

	if not settings.enabled:
		return

	# Get documents that have been sent but not yet delivered
	sent_docs = frappe.get_all(
		"Peppol Document Queue",
		filters={
			"status": ["in", ["Sent"]],
			"direction": "Outbound",
			"provider_document_id": ["is", "set"]
		},
		fields=["name", "provider", "provider_document_id"],
		limit=100  # Check 100 at a time
	)

	for queue_item in sent_docs:
		try:
			check_document_status(queue_item.name)
			frappe.db.commit()

		except Exception as e:
			frappe.log_error(
				f"Error checking status for {queue_item.name}: {str(e)}",
				"Peppol Status Checker"
			)
			frappe.db.rollback()


def check_document_status(queue_doc_name):
	"""
	Check status of a single document

	Args:
		queue_doc_name: Name of the Peppol Document Queue entry
	"""
	queue_doc = frappe.get_doc("Peppol Document Queue", queue_doc_name)

	if not queue_doc.provider_document_id:
		return

	try:
		# Get provider instance
		provider = get_provider_instance(queue_doc.provider)

		# Check status
		result = provider.get_document_status(queue_doc.provider_document_id)

		new_status = result.get("status")
		provider_status = result.get("provider_status")

		# Update queue entry if status changed
		if new_status and new_status != queue_doc.status:
			queue_doc.status = new_status
			queue_doc.last_status_check = now_datetime()

			if new_status == "Delivered":
				queue_doc.delivered_at = now_datetime()
			elif new_status == "Failed":
				queue_doc.failed_at = now_datetime()
				queue_doc.error_message = result.get("details", {}).get("error", "Delivery failed")

			queue_doc.save(ignore_permissions=True)

			# Update referenced document
			if queue_doc.reference_doctype and queue_doc.reference_name:
				try:
					ref_doc = frappe.get_doc(queue_doc.reference_doctype, queue_doc.reference_name)
					ref_doc.db_set("peppol_status", new_status, update_modified=False)

					if new_status == "Delivered":
						ref_doc.db_set("peppol_delivered_date", now_datetime(), update_modified=False)
					elif new_status == "Failed":
						ref_doc.db_set("peppol_error", queue_doc.error_message, update_modified=False)

				except Exception as e:
					frappe.log_error(f"Error updating reference document: {str(e)}", "Peppol Status")

		else:
			# Just update last check time
			queue_doc.db_set("last_status_check", now_datetime(), update_modified=False)

	except Exception as e:
		frappe.log_error(
			f"Error checking status for document {queue_doc_name}: {str(e)}",
			"Peppol Status Check Error"
		)
		raise
