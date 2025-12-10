// Add Peppol status indicator colors to Sales Invoice list view
frappe.listview_settings["Sales Invoice"] = frappe.listview_settings["Sales Invoice"] || {};
frappe.listview_settings["Sales Invoice"].formatters = frappe.listview_settings["Sales Invoice"].formatters || {};

frappe.listview_settings["Sales Invoice"].formatters.peppol_status = function(value) {
	const peppol_status_colors = {
		"Not Sent": "gray",
		"Queued": "orange",
		"Sending": "blue",
		"Sent": "blue",
		"Delivered": "green",
		"Failed": "red"
	};

	const color = peppol_status_colors[value] || "gray";
	return `<span class="indicator-pill ${color}"><span>${__(value)}</span></span>`;
};
