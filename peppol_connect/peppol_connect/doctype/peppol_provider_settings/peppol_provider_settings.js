// Copyright (c) 2025, Antoine Maas and contributors
// For license information, please see license.txt

frappe.ui.form.on("Peppol Provider", {
	refresh(frm) {
		// Add Test Connection button if the document is saved
		if (!frm.is_new()) {
			frm.add_custom_button(__('Test Connection'), function() {
				frappe.call({
					method: "test_connection",
					doc: frm.doc,
					callback: function(r) {
						if (r.message && r.message.success) {
							frappe.show_alert({
								message: __('Connection successful'),
								indicator: 'green'
							});
						}
					}
				});
			});
		}
	},

	provider_code(frm) {
		// Auto-fill provider name based on provider code
		if (frm.doc.provider_code) {
			const provider_names = {
				'recommand': 'Recommand'
			};
			if (provider_names[frm.doc.provider_code]) {
				frm.set_value('provider_name', provider_names[frm.doc.provider_code]);
			}
		}
	}
});
