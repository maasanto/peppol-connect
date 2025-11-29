"""Retry logic for failed Peppol transmissions"""

import frappe
from frappe.utils import now_datetime


def retry_failed_transmissions():
	"""
	Scheduled task to retry failed Peppol transmissions

	Finds all failed transmissions that:
	- Have retry enabled
	- Haven't exceeded max retry count
	- Have reached their next_retry_time

	Queues them for background processing
	"""
	from peppol_connect.api.send_invoice import process_transmission

	# Get retry settings
	settings = frappe.get_single("E Invoice Settings")
	retry_enabled = settings.get("peppol_retry_failed_sends", 0)

	if not retry_enabled:
		frappe.logger().debug("Peppol retry is disabled in E Invoice Settings")
		return

	max_retries = settings.get("peppol_max_retry_count", 3)

	# Find failed transmissions ready for retry
	transmissions = frappe.get_all(
		"Peppol Transmission",
		filters={
			"status": "Failed",
			"next_retry_time": ["<=", now_datetime()],
			"retry_count": ["<", max_retries]
		},
		pluck="name"
	)

	if not transmissions:
		frappe.logger().debug("No failed Peppol transmissions ready for retry")
		return

	frappe.logger().info(f"Found {len(transmissions)} failed Peppol transmissions to retry")

	# Queue each transmission for retry
	for transmission_name in transmissions:
		try:
			# Queue for background processing
			frappe.enqueue(
				"peppol_connect.api.send_invoice.process_transmission",
				transmission_name=transmission_name,
				queue="default",
				timeout=300
			)
			frappe.logger().info(f"Queued transmission {transmission_name} for retry")
		except Exception as e:
			frappe.log_error(
				f"Failed to queue transmission {transmission_name} for retry: {str(e)}",
				"Peppol Retry Queue Error"
			)

	frappe.db.commit()


@frappe.whitelist()
def retry_transmission(transmission_name):
	"""
	Manually retry a specific transmission

	Args:
		transmission_name: Name of the Peppol Transmission to retry

	Returns:
		dict: Success status and message
	"""
	from peppol_connect.api.send_invoice import process_transmission

	transmission = frappe.get_doc("Peppol Transmission", transmission_name)

	# Check if transmission can be retried
	if transmission.status != "Failed":
		return {
			"success": False,
			"message": f"Cannot retry transmission with status {transmission.status}"
		}

	settings = frappe.get_single("E Invoice Settings")
	max_retries = settings.get("peppol_max_retry_count", 3)

	if transmission.retry_count >= max_retries:
		return {
			"success": False,
			"message": f"Transmission has exceeded maximum retries ({max_retries})"
		}

	# Queue for retry
	frappe.enqueue(
		"peppol_connect.api.send_invoice.process_transmission",
		transmission_name=transmission_name,
		queue="default",
		timeout=300
	)

	return {
		"success": True,
		"message": f"Transmission {transmission_name} queued for retry"
	}
