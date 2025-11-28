# Copyright (c) 2025, Antoine Maas and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PeppolProvider(Document):
	def test_connection(self):
		"""Test the API connection using the provider adapter"""
		from peppol_connect.providers import get_provider_instance

		try:
			provider = get_provider_instance(self.provider_code)
			result = provider.test_connection()

			if result.get("success"):
				frappe.msgprint("Connection successful!", indicator="green")
			else:
				frappe.msgprint(
					f"Connection failed: {result.get('error', 'Unknown error')}",
					indicator="red"
				)

			return result

		except Exception as e:
			frappe.msgprint(f"Connection test failed: {str(e)}", indicator="red")
			frappe.log_error(f"Provider connection test failed: {str(e)}", "Peppol Provider")
			return {"success": False, "error": str(e)}
