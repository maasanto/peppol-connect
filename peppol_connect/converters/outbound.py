"""Convert ERPNext documents to Peppol/Recommand JSON format"""

import frappe
from frappe.utils import flt, getdate


def convert_sales_invoice_to_recommand(invoice_name):
	"""
	Convert ERPNext Sales Invoice to Recommand JSON format

	Args:
		invoice_name: Name of the Sales Invoice

	Returns:
		dict in Recommand JSON format
	"""
	invoice = frappe.get_doc("Sales Invoice", invoice_name)

	# Get customer and company
	customer = frappe.get_doc("Customer", invoice.customer)
	company = frappe.get_doc("Company", invoice.company)

	# Build the JSON structure
	recommand_json = {
		"invoiceNumber": invoice.name,
		"issueDate": getdate(invoice.posting_date).isoformat(),
		"currency": invoice.currency,
	}

	# Add due date if available
	if invoice.due_date:
		recommand_json["dueDate"] = getdate(invoice.due_date).isoformat()

	# Add buyer information
	recommand_json["buyer"] = _get_buyer_info(invoice, customer)

	# Add seller information
	recommand_json["seller"] = _get_seller_info(invoice, company)

	# Add invoice lines
	recommand_json["lines"] = _get_invoice_lines(invoice)

	# Add tax total
	recommand_json["taxTotal"] = {
		"amount": str(flt(invoice.total_taxes_and_charges, 2))
	}

	# Add totals
	recommand_json["legalMonetaryTotal"] = {
		"lineExtensionAmount": str(flt(invoice.net_total, 2)),
		"taxExclusiveAmount": str(flt(invoice.net_total, 2)),
		"taxInclusiveAmount": str(flt(invoice.grand_total, 2)),
		"payableAmount": str(flt(invoice.outstanding_amount or invoice.grand_total, 2))
	}

	# Add payment terms if available
	if invoice.payment_terms_template:
		recommand_json["paymentTerms"] = _get_payment_terms(invoice)

	# Add notes if available
	if invoice.customer_note or invoice.terms:
		recommand_json["notes"] = []
		if invoice.customer_note:
			recommand_json["notes"].append(invoice.customer_note)
		if invoice.terms:
			recommand_json["notes"].append(invoice.terms)

	return recommand_json


def _get_buyer_info(invoice, customer):
	"""Get buyer/customer information"""
	buyer = {
		"name": customer.customer_name or invoice.customer
	}

	# Add VAT number if available
	if customer.tax_id or invoice.tax_id:
		buyer["vatNumber"] = customer.tax_id or invoice.tax_id

	# Add address information
	if invoice.customer_address:
		try:
			address = frappe.get_doc("Address", invoice.customer_address)
			buyer.update({
				"street": address.address_line1 or "",
				"city": address.city or "",
				"postalZone": address.pincode or "",
				"country": address.country or ""
			})

			if address.address_line2:
				buyer["additionalStreet"] = address.address_line2

		except Exception as e:
			frappe.log_error(f"Error getting customer address: {str(e)}", "Peppol Converter")

	return buyer


def _get_seller_info(invoice, company):
	"""Get seller/company information"""
	seller = {
		"name": company.company_name
	}

	# Add VAT number if available
	if company.tax_id:
		seller["vatNumber"] = company.tax_id

	# Try to get company address
	try:
		# Get default company address
		address_links = frappe.get_all(
			"Dynamic Link",
			filters={
				"link_doctype": "Company",
				"link_name": company.name,
				"parenttype": "Address"
			},
			fields=["parent"]
		)

		if address_links:
			address = frappe.get_doc("Address", address_links[0].parent)
			seller.update({
				"street": address.address_line1 or "",
				"city": address.city or "",
				"postalZone": address.pincode or "",
				"country": address.country or ""
			})

			if address.address_line2:
				seller["additionalStreet"] = address.address_line2

	except Exception as e:
		frappe.log_error(f"Error getting company address: {str(e)}", "Peppol Converter")

	return seller


def _get_invoice_lines(invoice):
	"""Convert invoice items to Recommand line items"""
	lines = []

	for idx, item in enumerate(invoice.items, start=1):
		line = {
			"id": str(idx),
			"name": item.item_name or item.item_code,
			"quantity": str(flt(item.qty, 2)),
			"unitCode": item.uom or "C62",  # C62 = unit (piece)
			"netPriceAmount": str(flt(item.rate, 2)),
			"netAmount": str(flt(item.amount, 2))
		}

		# Add item description if available
		if item.description and item.description != item.item_name:
			line["description"] = item.description

		# Add VAT information
		vat_rate = "0.00"
		if item.item_tax_template:
			# Try to extract VAT rate from tax template
			try:
				tax_template = frappe.get_doc("Item Tax Template", item.item_tax_template)
				# Simplified: take the first tax rate
				if tax_template.taxes:
					vat_rate = str(flt(tax_template.taxes[0].tax_rate, 2))
			except:
				pass

		line["vat"] = {
			"percentage": vat_rate,
			"amount": str(flt(item.amount * flt(vat_rate) / 100, 2))
		}

		lines.append(line)

	return lines


def _get_payment_terms(invoice):
	"""Get payment terms information"""
	payment_terms = []

	if invoice.payment_terms_template:
		try:
			template = frappe.get_doc("Payment Terms Template", invoice.payment_terms_template)

			for term in template.terms:
				payment_term = {
					"note": term.description or ""
				}

				# Add due date calculation if available
				if term.credit_days:
					payment_term["paymentDueDays"] = term.credit_days

				payment_terms.append(payment_term)

		except Exception as e:
			frappe.log_error(f"Error getting payment terms: {str(e)}", "Peppol Converter")

	return payment_terms
