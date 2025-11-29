"""Factory for creating Peppol provider instances"""

import frappe


def get_provider_instance(provider_name=None):
	"""
	Get a provider instance based on provider settings

	Args:
		provider_name: Name of Peppol Provider Settings record
		             If None, uses default from E Invoice Settings

	Returns:
		BasePeppolProvider: Provider instance

	Raises:
		Exception: If provider not found or not supported
	"""
	# Get provider name from settings if not provided
	if not provider_name:
		settings = frappe.get_single("E Invoice Settings")
		if not settings.get("peppol_enabled"):
			frappe.throw("Peppol Connect is not enabled in E Invoice Settings")

		provider_name = settings.get("peppol_provider")
		if not provider_name:
			frappe.throw("No Peppol Provider configured in E Invoice Settings")

	# Get provider settings
	provider_settings = frappe.get_doc("Peppol Provider Settings", provider_name)

	if not provider_settings.enabled:
		frappe.throw(f"Peppol Provider '{provider_name}' is not enabled")

	# Get provider code
	provider_code = provider_settings.provider_code

	# Factory pattern - create appropriate provider instance
	if provider_code == "recommand":
		from peppol_connect.providers.recommand_provider import RecommandProvider
		return RecommandProvider(provider_settings)
	else:
		frappe.throw(f"Provider '{provider_code}' is not yet supported")


def get_supported_providers():
	"""
	Get list of supported provider codes

	Returns:
		list: List of supported provider codes
	"""
	return ["recommand"]
