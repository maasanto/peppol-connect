"""API endpoint for verifying Peppol recipients"""

import frappe
from frappe import _


@frappe.whitelist()
def verify_peppol_recipient(customer_name=None, peppol_id=None):
	"""
	Verify if a Peppol recipient is reachable on the network

	Args:
		customer_name: Name of Customer document (optional)
		peppol_id: Peppol ID in format "scheme:id" (optional)

	One of customer_name or peppol_id must be provided

	Returns:
		dict: {
			"reachable": bool,
			"participant_id": str,
			"message": str,
			"details": dict
		}
	"""
	from peppol_connect.providers.provider_factory import get_provider_instance
	from peppol_connect.utils.peppol_utils import get_peppol_address

	# Get Peppol ID
	if customer_name:
		# Get Peppol ID from Customer
		peppol_id = get_peppol_address(customer_name)
		if not peppol_id:
			return {
				"reachable": False,
				"participant_id": None,
				"message": _("Customer {0} does not have a valid Peppol ID configured").format(customer_name),
				"details": {}
			}
	elif not peppol_id:
		frappe.throw(_("Either customer_name or peppol_id must be provided"))

	# Get provider
	settings = frappe.get_single("E Invoice Settings")
	if not settings.get("peppol_enabled"):
		frappe.throw(_("Peppol is not enabled in E Invoice Settings"))

	if not settings.get("peppol_provider"):
		frappe.throw(_("No Peppol Provider configured in E Invoice Settings"))

	try:
		provider = get_provider_instance(settings.peppol_provider)

		result = provider.verify_recipient(peppol_id)

		# Add user-friendly message
		if result.get("reachable"):
			message = _("Recipient {0} is reachable on the Peppol network").format(peppol_id)
			result["message"] = message
		else:
			result["message"] = _("Recipient {0} is not reachable on the Peppol network").format(peppol_id)

		return result

	except Exception as e:
		frappe.log_error(f"Failed to verify Peppol recipient {peppol_id}: {str(e)}", "Peppol Verification Error")
		return {
			"reachable": False,
			"participant_id": peppol_id,
			"message": _("Error verifying recipient: {0}").format(str(e)),
			"details": {"error": str(e)}
		}
