"""Peppol Provider Adapters"""

from peppol_connect.providers.recommand import RecommandProvider


def get_provider_instance(provider_code):
	"""
	Get an instance of a provider adapter

	Args:
		provider_code: The provider code (e.g., "recommand")

	Returns:
		Provider instance

	Raises:
		ValueError: If provider not supported
	"""
	import frappe

	# Simple mapping of provider codes to classes
	provider_classes = {
		"recommand": RecommandProvider,
		# Add more providers here as they are implemented
		# "storecove": StorecoveProvider,
	}

	if provider_code not in provider_classes:
		raise ValueError(f"Unsupported provider: {provider_code}")

	# Get the provider document
	provider_doc = frappe.get_doc("Peppol Provider", provider_code)

	# Instantiate the provider class
	provider_class = provider_classes[provider_code]
	return provider_class(provider_doc)
