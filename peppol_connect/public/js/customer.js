frappe.ui.form.on('Customer', {
	refresh(frm) {
		// Only show verification button if customer has Peppol info configured
		if (frm.doc.electronic_address_scheme && frm.doc.electronic_address) {
			// Check if Peppol is enabled
			frappe.db.get_single_value('E Invoice Settings', 'peppol_enabled')
				.then(peppol_enabled => {
					if (peppol_enabled) {
						frm.add_custom_button(__('Verify Peppol ID'), function() {
							verify_peppol_id(frm);
						}, __('Actions'));
					}
				});
		}
	}
});

function verify_peppol_id(frm) {
	frappe.call({
		method: 'peppol_connect.api.verify.verify_peppol_recipient',
		args: {
			customer_name: frm.doc.name
		},
		freeze: true,
		freeze_message: __('Verifying Peppol ID...'),
		callback: function(r) {
			if (r.message) {
				let indicator = r.message.reachable ? 'green' : 'red';
				let title = r.message.reachable ? __('Reachable') : __('Not Reachable');

				frappe.msgprint({
					title: title,
					message: r.message.message,
					indicator: indicator
				});

				// Show additional details if available
				if (r.message.details && Object.keys(r.message.details).length > 0) {
					console.log('Peppol Verification Details:', r.message.details);
				}
			}
		},
		error: function(r) {
			frappe.msgprint({
				title: __('Error'),
				message: __('Failed to verify Peppol ID. Please check the error log.'),
				indicator: 'red'
			});
		}
	});
}
