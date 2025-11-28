"""Background task to process outbound Peppol document queue"""

import frappe
from frappe.utils import now_datetime, add_to_date
from peppol_connect.providers import get_provider_instance
import json


def process_outbound_queue():
	"""
	Process queued outbound Peppol documents
	This function is called by the scheduler
	"""
	settings = frappe.get_single("Peppol Settings")

	if not settings.enabled:
		return

	# Get queued documents
	queued_docs = frappe.get_all(
		"Peppol Document Queue",
		filters={
			"status": ["in", ["Queued", "Failed"]],
			"direction": "Outbound"
		},
		fields=["name", "retry_count", "next_retry_time"],
		order_by="queued_at asc",
		limit=50  # Process 50 at a time
	)

	for queue_item in queued_docs:
		# Check if we should retry failed items
		if queue_item.get("retry_count") and queue_item.get("retry_count") > 0:
			if not settings.retry_failed_sends:
				continue

			# Check if max retries exceeded
			if queue_item.get("retry_count") >= settings.max_retry_count:
				continue

			# Check if it's time to retry
			if queue_item.get("next_retry_time") and queue_item.get("next_retry_time") > now_datetime():
				continue

		try:
			send_document(queue_item.name)
			frappe.db.commit()

		except Exception as e:
			frappe.log_error(
				f"Error processing queue item {queue_item.name}: {str(e)}",
				"Peppol Queue Processor"
			)
			frappe.db.rollback()


def send_document(queue_doc_name):
	"""
	Send a single document from the queue

	Args:
		queue_doc_name: Name of the Peppol Document Queue entry
	"""
	queue_doc = frappe.get_doc("Peppol Document Queue", queue_doc_name)

	# Update status to sending
	queue_doc.status = "Sending"
	queue_doc.save(ignore_permissions=True)

	try:
		# Get provider instance
		provider = get_provider_instance(queue_doc.provider)

		# Parse the JSON document
		document_json = json.loads(queue_doc.peppol_json)

		# Send document
		result = provider.send_document(
			document=document_json,
			recipient_peppol_id=queue_doc.recipient_peppol_id,
			document_type=queue_doc.document_type
		)

		# Update queue entry
		queue_doc.provider_document_id = result.get("provider_document_id")
		queue_doc.status = "Sent"
		queue_doc.sent_at = now_datetime()
		queue_doc.error_message = None
		queue_doc.save(ignore_permissions=True)

		# Update referenced document (e.g., Sales Invoice)
		if queue_doc.reference_doctype and queue_doc.reference_name:
			try:
				ref_doc = frappe.get_doc(queue_doc.reference_doctype, queue_doc.reference_name)
				ref_doc.db_set("peppol_status", "Sent", update_modified=False)
				ref_doc.db_set("peppol_document_id", result.get("provider_document_id"), update_modified=False)
				ref_doc.db_set("peppol_sent_date", now_datetime(), update_modified=False)
				ref_doc.db_set("peppol_error", None, update_modified=False)
			except Exception as e:
				frappe.log_error(f"Error updating reference document: {str(e)}", "Peppol Queue")

		frappe.log_error(
			f"Successfully sent document {queue_doc_name} to Peppol network",
			"Peppol Send Success"
		)

	except Exception as e:
		error_msg = str(e)

		# Increment retry count
		retry_count = (queue_doc.retry_count or 0) + 1

		# Calculate next retry time (exponential backoff)
		next_retry = add_to_date(now_datetime(), minutes=5 * (2 ** retry_count))

		# Update queue entry
		queue_doc.status = "Failed"
		queue_doc.error_message = error_msg
		queue_doc.retry_count = retry_count
		queue_doc.next_retry_time = next_retry
		queue_doc.failed_at = now_datetime()
		queue_doc.save(ignore_permissions=True)

		# Update referenced document
		if queue_doc.reference_doctype and queue_doc.reference_name:
			try:
				ref_doc = frappe.get_doc(queue_doc.reference_doctype, queue_doc.reference_name)
				ref_doc.db_set("peppol_status", "Failed", update_modified=False)
				ref_doc.db_set("peppol_error", error_msg, update_modified=False)
			except:
				pass

		frappe.log_error(
			f"Failed to send document {queue_doc_name}: {error_msg}",
			"Peppol Send Error"
		)

		raise
