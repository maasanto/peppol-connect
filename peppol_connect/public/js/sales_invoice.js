frappe.ui.form.on('Sales Invoice', {
	refresh(frm) {
		// Only show the button if the invoice is submitted
		if (frm.doc.docstatus === 1) {
			// Get Peppol settings
			frappe.db.get_single_value('E Invoice Settings', 'peppol_enabled')
				.then(peppol_enabled => {
					if (peppol_enabled) {
						// Add "Send to Peppol" button
						frm.add_custom_button(__('Send to Peppol'), function() {
							send_to_peppol(frm);
						});

						// Add "Refresh Peppol Status" button if already sent
						if (frm.doc.peppol_status && frm.doc.peppol_status !== 'Not Sent') {
							frm.add_custom_button(__('Refresh Peppol Status'), function() {
								refresh_peppol_status(frm);
							}, __('Actions'));
						}

						// Add "Retry Peppol Send" button if failed
						if (frm.doc.peppol_status === 'Failed' && frm.doc.peppol_transmission_id) {
							frm.add_custom_button(__('Retry Peppol Send'), function() {
								retry_peppol_send(frm);
							}, __('Actions'));
						}
					}
				});
		}
	}
});

function send_to_peppol(frm) {
	frappe.confirm(
		__('Are you sure you want to send this invoice via Peppol?'),
		function() {
			frappe.call({
				method: 'peppol_connect.api.send_invoice.send_to_peppol',
				args: {
					sales_invoice_name: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Sending to Peppol...'),
				callback: function(r) {
					if (r.message) {
						frappe.show_alert({
							message: __('Invoice queued for Peppol transmission'),
							indicator: 'green'
						});
						frm.reload_doc();
					}
				},
				error: function(r) {
					frappe.msgprint({
						title: __('Error'),
						message: __('Failed to send invoice to Peppol. Please check the error log.'),
						indicator: 'red'
					});
				}
			});
		}
	);
}

function refresh_peppol_status(frm) {
	if (!frm.doc.peppol_transmission_id) {
		frappe.msgprint(__('No Peppol transmission found for this invoice'));
		return;
	}

	frappe.call({
		method: 'peppol_connect.api.check_status.check_transmission_status',
		args: {
			transmission_name: frm.doc.peppol_transmission_id
		},
		freeze: true,
		freeze_message: __('Checking Peppol status...'),
		callback: function(r) {
			if (r.message) {
				frappe.show_alert({
					message: __('Peppol status updated'),
					indicator: 'blue'
				});
				frm.reload_doc();
			}
		}
	});
}

function retry_peppol_send(frm) {
	if (!frm.doc.peppol_transmission_id) {
		frappe.msgprint(__('No Peppol transmission found for this invoice'));
		return;
	}

	frappe.confirm(
		__('Are you sure you want to retry sending this invoice via Peppol?'),
		function() {
			frappe.call({
				method: 'peppol_connect.api.retry.retry_transmission',
				args: {
					transmission_name: frm.doc.peppol_transmission_id
				},
				freeze: true,
				freeze_message: __('Retrying Peppol send...'),
				callback: function(r) {
					if (r.message && r.message.success) {
						frappe.show_alert({
							message: r.message.message || __('Transmission queued for retry'),
							indicator: 'green'
						});
						frm.reload_doc();
					} else if (r.message) {
						frappe.msgprint({
							title: __('Cannot Retry'),
							message: r.message.message,
							indicator: 'orange'
						});
					}
				},
				error: function(r) {
					frappe.msgprint({
						title: __('Error'),
						message: __('Failed to retry Peppol send. Please check the error log.'),
						indicator: 'red'
					});
				}
			});
		}
	);
}
