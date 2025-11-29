"""API endpoint and scheduled task for checking Peppol transmission status"""

import frappe
from frappe.utils import now_datetime


def check_pending_transmissions():
	"""
	Scheduled task to check status of pending transmissions
	Called by scheduler every 15 minutes
	"""
	settings = frappe.get_single("E Invoice Settings")

	if not settings.get("peppol_enabled"):
		return

	# Get transmissions that are sent but not yet delivered
	transmissions = frappe.get_all(
		"Peppol Transmission",
		filters={
			"status": ["in", ["Sent"]],
			"direction": "Outbound",
			"provider_document_id": ["is", "set"]
		},
		fields=["name", "provider", "provider_document_id"],
		limit=100
	)

	for trans in transmissions:
		try:
			check_transmission_status(trans.name)
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(
				f"Error checking status for {trans.name}: {str(e)}",
				"Peppol Status Check Error"
			)
			frappe.db.rollback()


def check_transmission_status(transmission_name):
	"""
	Check status of a single transmission

	Args:
		transmission_name: Name of Peppol Transmission record
	"""
	from peppol_connect.providers.provider_factory import get_provider_instance

	transmission = frappe.get_doc("Peppol Transmission", transmission_name)

	if not transmission.provider_document_id:
		return

	try:
		# Get provider
		provider = get_provider_instance(transmission.provider)

		# Check status
		result = provider.get_document_status(transmission.provider_document_id)
		new_status = result.get("status")

		# Update if status changed
		if new_status and new_status != transmission.status:
			transmission.status = new_status
			transmission.last_status_check = now_datetime()

			if new_status == "Delivered":
				transmission.delivered_at = now_datetime()
			elif new_status == "Failed":
				transmission.failed_at = now_datetime()
				transmission.error_message = result.get("error", "Delivery failed")

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
		else:
			# Just update last check time
			transmission.db_set("last_status_check", now_datetime(), update_modified=False)

	except Exception as e:
		frappe.log_error(
			f"Error checking transmission status: {str(e)}",
			f"Peppol Status Error - {transmission_name}"
		)
		raise


@frappe.whitelist()
def manual_status_check(transmission_name):
	"""
	Manual status check from UI

	Args:
		transmission_name: Name of Peppol Transmission record

	Returns:
		dict: {"success": bool, "status": str, "message": str}
	"""
	try:
		check_transmission_status(transmission_name)
		frappe.db.commit()

		transmission = frappe.get_doc("Peppol Transmission", transmission_name)

		return {
			"success": True,
			"status": transmission.status,
			"message": f"Status updated to: {transmission.status}"
		}
	except Exception as e:
		frappe.log_error(f"Manual status check failed: {str(e)}", f"Peppol Status Check - {transmission_name}")
		return {
			"success": False,
			"message": str(e)
		}
