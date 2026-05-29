from collections import defaultdict

import frappe
from frappe.utils import add_days, cint, date_diff, flt, nowdate


SOURCE = {
    "key": "current_site",
    "label": "Current ERPNext site",
    "type": "frappe_local",
}


def _limit(value, default=20, maximum=100):
    value = cint(value) or default
    return max(1, min(value, maximum))


def _like(value):
    return f"%{value or ''}%"


def _round_money(value):
    return round(flt(value), 2)


def _first_exact(doctype, names):
    for name in [value for value in names if value]:
        if frappe.db.exists(doctype, name):
            return frappe.get_doc(doctype, name)
    return None


def _parse_payload(payload):
    if isinstance(payload, str):
        payload = frappe.parse_json(payload)
    return payload or {}


def _document_route(doctype, name):
    return f"/app/{frappe.scrub(doctype).replace('_', '-')}/{name}"


def _linked_docnames(customer, doctype):
    links = frappe.get_all(
        "Dynamic Link",
        filters={
            "link_doctype": "Customer",
            "link_name": customer,
            "parenttype": doctype,
        },
        fields=["parent"],
        limit_page_length=100,
    )
    return sorted({link.parent for link in links if link.parent})


def _required_customer(payload):
    customer = payload.get("customer") or payload.get("customer_name")
    if not customer:
        frappe.throw("Customer is required.")
    return customer


def _default_company():
    return (
        frappe.defaults.get_user_default("Company")
        or frappe.defaults.get_global_default("company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )


def _validate_link(doctype, value, label=None):
    if value and not frappe.db.exists(doctype, value):
        frappe.throw(f"{label or doctype} does not exist: {value}")


def _normalized_basket_items(payload):
    items = payload.get("items") or []
    if isinstance(items, str):
        items = frappe.parse_json(items)

    if not items:
        frappe.throw("At least one item is required.")

    rows = []
    for index, item in enumerate(items, start=1):
        item_code = item.get("item_code") or item.get("item") or item.get("item_name")
        if not item_code:
            frappe.throw(f"Item code is required on line {index}.")

        qty = flt(item.get("qty") or item.get("quantity") or 1)
        if qty <= 0:
            frappe.throw(f"Quantity must be greater than zero on line {index}.")

        row = {
            "item_code": item_code,
            "qty": qty,
        }
        _validate_link("Item", item_code, f"Item on line {index}")

        if item.get("rate") is not None:
            row["rate"] = flt(item.get("rate"))
        elif item.get("unit_rate") is not None:
            row["rate"] = flt(item.get("unit_rate"))

        if item.get("uom"):
            row["uom"] = item.get("uom")
        if item.get("description"):
            row["description"] = item.get("description")
        if item.get("warehouse"):
            _validate_link("Warehouse", item.get("warehouse"), f"Warehouse on line {index}")
            row["warehouse"] = item.get("warehouse")
        if item.get("delivery_date"):
            row["delivery_date"] = item.get("delivery_date")

        rows.append(row)

    return rows


def _apply_optional_selling_fields(doc, payload):
    company = payload.get("company") or _default_company()
    if company:
        _validate_link("Company", company, "Company")
        if doc.meta.has_field("company"):
            doc.company = company

    if payload.get("selling_price_list"):
        _validate_link("Price List", payload.get("selling_price_list"), "Selling Price List")
    if payload.get("taxes_and_charges"):
        _validate_link("Sales Taxes and Charges Template", payload.get("taxes_and_charges"), "Taxes and Charges")

    optional_fields = {
        "currency": "currency",
        "selling_price_list": "selling_price_list",
        "price_list_currency": "price_list_currency",
        "conversion_rate": "conversion_rate",
        "plc_conversion_rate": "plc_conversion_rate",
        "taxes_and_charges": "taxes_and_charges",
        "terms": "terms",
    }

    for payload_key, doc_field in optional_fields.items():
        if payload.get(payload_key) is not None and doc.meta.has_field(doc_field):
            doc.set(doc_field, payload.get(payload_key))

    notes = payload.get("notes") or payload.get("remarks")
    if notes and doc.meta.has_field("remarks"):
        doc.remarks = notes


def _sales_invoice_item_rows(customer=None, item=None, limit=None):
    conditions = ["si.docstatus = 1"]
    values = {}

    if customer:
        conditions.append("si.customer = %(customer)s")
        values["customer"] = customer

    if item:
        conditions.append("(sii.item_code = %(item)s OR sii.item_name = %(item)s)")
        values["item"] = item

    limit_clause = ""
    if limit:
        limit_clause = "LIMIT %(limit)s"
        values["limit"] = _limit(limit, maximum=500)

    return frappe.db.sql(
        f"""
        SELECT
            si.name AS sales_invoice,
            si.customer,
            si.customer_name,
            si.posting_date,
            si.currency,
            sii.item_code,
            sii.item_name,
            sii.description,
            sii.item_group,
            sii.uom,
            sii.qty,
            sii.rate,
            sii.amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {" AND ".join(conditions)}
        ORDER BY si.posting_date DESC, si.modified DESC
        {limit_clause}
        """,
        values,
        as_dict=True,
    )


def _item_purchase_summary(rows):
    summary = {}
    for row in rows:
        key = row.item_code or row.item_name
        if not key:
            continue

        current = summary.setdefault(
            key,
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "item_group": row.item_group,
                "uom": row.uom,
                "total_qty": 0,
                "total_amount": 0,
                "purchase_count": 0,
                "rates": [],
                "last_rate": None,
                "last_purchase_date": None,
            },
        )
        current["total_qty"] += flt(row.qty)
        current["total_amount"] += flt(row.amount)
        current["purchase_count"] += 1
        current["rates"].append(flt(row.rate))

        if not current["last_purchase_date"] or row.posting_date > current["last_purchase_date"]:
            current["last_purchase_date"] = row.posting_date
            current["last_rate"] = flt(row.rate)

    items = []
    for item in summary.values():
        rates = item.pop("rates")
        item["avg_rate"] = _round_money(sum(rates) / len(rates)) if rates else 0
        item["last_rate"] = _round_money(item["last_rate"])
        item["total_qty"] = _round_money(item["total_qty"])
        item["total_amount"] = _round_money(item["total_amount"])
        item["last_purchase_date"] = str(item["last_purchase_date"]) if item["last_purchase_date"] else None
        items.append(item)

    return sorted(items, key=lambda row: row["total_amount"], reverse=True)


def _quote_rate_summary(rows):
    rates = [flt(row.rate) for row in rows if flt(row.rate) > 0]
    if not rates:
        return None

    rate_frequency = defaultdict(int)
    for rate in rates:
        rate_frequency[_round_money(rate)] += 1

    most_common_rate = sorted(rate_frequency.items(), key=lambda item: (-item[1], item[0]))[0][0]
    most_recent = rows[0] if rows else None

    return {
        "minimum_rate": _round_money(min(rates)),
        "average_rate": _round_money(sum(rates) / len(rates)),
        "most_common_rate": _round_money(most_common_rate),
        "most_recent_rate": _round_money(most_recent.rate if most_recent else 0),
        "maximum_rate": _round_money(max(rates)),
        "distinct_rates": len(rate_frequency),
        "rate_frequency": rate_frequency[most_common_rate],
        "most_recent_sale_date": str(most_recent.posting_date) if most_recent else None,
    }


def _customer_item_codes(customer):
    rows = _sales_invoice_item_rows(customer=customer)
    return {row.item_code for row in rows if row.item_code}


def _repeat_purchase_reminders(customer, exclude_item_codes=None, stale_after_days=90, limit=10):
    exclude_item_codes = set(exclude_item_codes or [])
    reminders = []

    for item in _item_purchase_summary(_sales_invoice_item_rows(customer=customer)):
        item_code = item.get("item_code")
        last_purchase_date = item.get("last_purchase_date")
        if not item_code or item_code in exclude_item_codes or not last_purchase_date:
            continue
        if date_diff(nowdate(), last_purchase_date) < stale_after_days:
            continue

        reminders.append(
            {
                "item_code": item_code,
                "item_name": item.get("item_name"),
                "suggested_rate": item.get("last_rate") or item.get("avg_rate") or 0,
                "last_purchase_date": last_purchase_date,
                "reason": f"Bought before, but not purchased in the last {stale_after_days} days.",
                "source": SOURCE,
                "recommendation_type": "repeat_purchase",
            }
        )

    return reminders[: _limit(limit)]


def _frequently_bought_with(item_codes, exclude_item_codes=None, limit=10):
    item_codes = [code for code in item_codes if code]
    if not item_codes:
        return []

    exclude_item_codes = set(exclude_item_codes or [])
    rows = frappe.db.sql(
        """
        SELECT
            other.item_code,
            other.item_name,
            COUNT(DISTINCT si.customer) AS customer_overlap,
            COUNT(DISTINCT si.name) AS document_overlap,
            AVG(other.rate) AS average_rate,
            MAX(si.posting_date) AS most_recent_sale_date
        FROM `tabSales Invoice Item` selected
        INNER JOIN `tabSales Invoice` si ON si.name = selected.parent AND si.docstatus = 1
        INNER JOIN `tabSales Invoice Item` other ON other.parent = si.name
        WHERE selected.item_code IN %(item_codes)s
          AND other.item_code NOT IN %(item_codes)s
        GROUP BY other.item_code, other.item_name
        ORDER BY customer_overlap DESC, document_overlap DESC, most_recent_sale_date DESC
        LIMIT %(limit)s
        """,
        {
            "item_codes": tuple(item_codes),
            "limit": _limit(limit),
        },
        as_dict=True,
    )

    recommendations = []
    for row in rows:
        if row.item_code in exclude_item_codes:
            continue
        recommendations.append(
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "customer_overlap": cint(row.customer_overlap),
                "document_overlap": cint(row.document_overlap),
                "suggested_rate": _round_money(row.average_rate),
                "most_recent_sale_date": str(row.most_recent_sale_date) if row.most_recent_sale_date else None,
                "reason": "Frequently bought with this customer's purchased items.",
                "source": SOURCE,
            }
        )

    return recommendations[: _limit(limit)]


def _contact_summary(contact_name):
    contact = frappe.get_doc("Contact", contact_name)
    phones = []
    emails = []

    for row in getattr(contact, "phone_nos", []) or []:
        phones.append(
            {
                "phone": row.get("phone"),
                "is_primary_phone": bool(row.get("is_primary_phone")),
                "is_primary_mobile": bool(row.get("is_primary_mobile")),
            }
        )

    for row in getattr(contact, "email_ids", []) or []:
        emails.append(
            {
                "email_id": row.get("email_id"),
                "is_primary": bool(row.get("is_primary")),
            }
        )

    if contact.get("phone") and not any(row["phone"] == contact.get("phone") for row in phones):
        phones.append({"phone": contact.get("phone"), "is_primary_phone": True, "is_primary_mobile": False})
    if contact.get("mobile_no") and not any(row["phone"] == contact.get("mobile_no") for row in phones):
        phones.append({"phone": contact.get("mobile_no"), "is_primary_phone": False, "is_primary_mobile": True})
    if contact.get("email_id") and not any(row["email_id"] == contact.get("email_id") for row in emails):
        emails.append({"email_id": contact.get("email_id"), "is_primary": True})

    return {
        "contact": contact.name,
        "first_name": contact.get("first_name"),
        "last_name": contact.get("last_name"),
        "full_name": contact.get("full_name"),
        "designation": contact.get("designation"),
        "department": contact.get("department"),
        "phones": phones,
        "emails": emails,
        "route": _document_route("Contact", contact.name),
    }


def _linked_contacts(customer):
    return [_contact_summary(name) for name in _linked_docnames(customer, "Contact")]


def _address_summary(address_name):
    address = frappe.get_doc("Address", address_name)
    lines = [
        address.get("address_line1"),
        address.get("address_line2"),
        address.get("city"),
        address.get("state"),
        address.get("country"),
    ]

    return {
        "address": address.name,
        "address_title": address.get("address_title"),
        "address_type": address.get("address_type"),
        "display": ", ".join([line for line in lines if line]),
        "city": address.get("city"),
        "state": address.get("state"),
        "country": address.get("country"),
        "pincode": address.get("pincode"),
        "email_id": address.get("email_id"),
        "phone": address.get("phone"),
        "fax": address.get("fax"),
        "route": _document_route("Address", address.name),
    }


def _linked_addresses(customer):
    return [_address_summary(name) for name in _linked_docnames(customer, "Address")]


def _linked_accounts(customer_doc):
    accounts = []
    for row in getattr(customer_doc, "accounts", []) or []:
        accounts.append(
            {
                "company": row.get("company"),
                "account": row.get("account"),
            }
        )
    return accounts


def _recent_documents(doctype, filters, date_field, limit=5):
    fields = ["name", "docstatus", "status", "currency", "grand_total", date_field]
    rows = frappe.get_all(
        doctype,
        filters=filters,
        fields=fields,
        order_by=f"{date_field} desc, modified desc",
        limit_page_length=_limit(limit),
    )

    data = []
    for row in rows:
        data.append(
            {
                "doctype": doctype,
                "name": row.name,
                "date": str(row.get(date_field)) if row.get(date_field) else None,
                "status": row.status,
                "docstatus": row.docstatus,
                "currency": row.currency,
                "grand_total": _round_money(row.grand_total),
                "route": _document_route(doctype, row.name),
            }
        )
    return data


def _recent_customer_transactions(customer):
    return {
        "quotations": _recent_documents("Quotation", {"party_name": customer}, "transaction_date"),
        "sales_orders": _recent_documents("Sales Order", {"customer": customer}, "transaction_date"),
        "sales_invoices": _recent_documents("Sales Invoice", {"customer": customer}, "posting_date"),
    }


def search_customers(search=None, limit=20):
    or_filters = None
    if search:
        or_filters = {
            "name": ["like", _like(search)],
            "customer_name": ["like", _like(search)],
        }

    rows = frappe.get_all(
        "Customer",
        or_filters=or_filters,
        fields=["name", "customer_name", "customer_type", "customer_group", "territory"],
        order_by="modified desc",
        limit_page_length=_limit(limit),
    )

    data = []
    for row in rows:
        data.append(
            {
                "customer_id": row.name,
                "customer": row.name,
                "customer_name": row.customer_name,
                "customer_type": row.customer_type,
                "customer_group": row.customer_group,
                "territory": row.territory,
                "source": SOURCE,
            }
        )

    return {"count": len(data), "data": data, "source": SOURCE}


def match_customer(customer=None, customer_name=None, limit=5):
    exact = _first_exact("Customer", [customer, customer_name])
    candidates = []

    search = customer_name or customer
    if search:
        rows = frappe.get_all(
            "Customer",
            or_filters={
                "name": ["like", _like(search)],
                "customer_name": ["like", _like(search)],
            },
            fields=["name", "customer_name", "customer_group", "territory"],
            order_by="modified desc",
            limit_page_length=_limit(limit),
        )
        candidates = [
            {
                "customer": row.name,
                "customer_name": row.customer_name,
                "customer_group": row.customer_group,
                "territory": row.territory,
                "source": SOURCE,
            }
            for row in rows
        ]

    return {
        "matched": bool(exact),
        "customer": exact.name if exact else None,
        "customer_name": exact.customer_name if exact else None,
        "candidates": candidates,
        "source": SOURCE,
    }


def match_item(item_code=None, item_name=None, limit=5):
    exact = _first_exact("Item", [item_code, item_name])
    candidates = []

    search = item_name or item_code
    if search:
        rows = frappe.get_all(
            "Item",
            filters={"disabled": 0},
            or_filters={
                "name": ["like", _like(search)],
                "item_code": ["like", _like(search)],
                "item_name": ["like", _like(search)],
            },
            fields=["name", "item_code", "item_name", "item_group", "stock_uom"],
            order_by="modified desc",
            limit_page_length=_limit(limit),
        )
        candidates = [
            {
                "item_code": row.item_code or row.name,
                "item_name": row.item_name,
                "item_group": row.item_group,
                "stock_uom": row.stock_uom,
                "source": SOURCE,
            }
            for row in rows
        ]

    return {
        "matched": bool(exact),
        "item_code": exact.item_code if exact else None,
        "item_name": exact.item_name if exact else None,
        "candidates": candidates,
        "source": SOURCE,
    }


def get_customer_summary(customer):
    customer_doc = frappe.get_doc("Customer", customer)
    rows = _sales_invoice_item_rows(customer=customer)
    items = _item_purchase_summary(rows)
    item_codes = [item["item_code"] for item in items if item.get("item_code")]

    total_qty = sum(flt(item["total_qty"]) for item in items)
    total_amount = sum(flt(item["total_amount"]) for item in items)
    recommendations = _frequently_bought_with(item_codes, exclude_item_codes=item_codes, limit=10)

    return {
        "customer": customer_doc.name,
        "customer_name": customer_doc.customer_name,
        "customer_type": customer_doc.customer_type,
        "customer_group": customer_doc.customer_group,
        "territory": customer_doc.territory,
        "item_count": len(items),
        "total_qty": _round_money(total_qty),
        "total_amount": _round_money(total_amount),
        "total_purchase_count": len(rows),
        "items": items,
        "contacts": _linked_contacts(customer),
        "addresses": _linked_addresses(customer),
        "accounts": _linked_accounts(customer_doc),
        "recent_transactions": _recent_customer_transactions(customer),
        "cross_sell_suggestions": recommendations,
        "source": SOURCE,
    }


def search_items(search=None, limit=20):
    filters = {"disabled": 0}
    or_filters = None
    if search:
        or_filters = {
            "name": ["like", _like(search)],
            "item_code": ["like", _like(search)],
            "item_name": ["like", _like(search)],
        }

    rows = frappe.get_all(
        "Item",
        filters=filters,
        or_filters=or_filters,
        fields=["name", "item_code", "item_name", "item_group", "stock_uom"],
        order_by="modified desc",
        limit_page_length=_limit(limit),
    )

    data = []
    for row in rows:
        history = _sales_invoice_item_rows(item=row.name, limit=100)
        rate_summary = _quote_rate_summary(history)
        data.append(
            {
                "item_id": row.name,
                "item_code": row.item_code,
                "item_name": row.item_name,
                "item_group": row.item_group,
                "stock_uom": row.stock_uom,
                "avg_rate": rate_summary["average_rate"] if rate_summary else 0,
                "last_rate": rate_summary["most_recent_rate"] if rate_summary else 0,
                "purchase_count": len(history),
                "source": SOURCE,
            }
        )

    return {"count": len(data), "data": data, "source": SOURCE}


def get_item_summary(item):
    item_doc = frappe.get_doc("Item", item)
    history = _sales_invoice_item_rows(item=item, limit=200)
    customers = defaultdict(lambda: {"purchase_count": 0, "total_qty": 0, "total_amount": 0})

    for row in history:
        current = customers[row.customer]
        current["customer"] = row.customer
        current["customer_name"] = row.customer_name
        current["purchase_count"] += 1
        current["total_qty"] += flt(row.qty)
        current["total_amount"] += flt(row.amount)

    top_customers = sorted(customers.values(), key=lambda row: row["total_amount"], reverse=True)[:10]
    for row in top_customers:
        row["total_qty"] = _round_money(row["total_qty"])
        row["total_amount"] = _round_money(row["total_amount"])

    return {
        "item_id": item_doc.name,
        "item_code": item_doc.item_code,
        "item_name": item_doc.item_name,
        "item_group": item_doc.item_group,
        "stock_uom": item_doc.stock_uom,
        "quote_rate_summary": _quote_rate_summary(history),
        "pricing_history": history[:25],
        "top_customers": top_customers,
        "source": SOURCE,
    }


def pricing_lookup(customer, item):
    customer_history = _sales_invoice_item_rows(customer=customer, item=item, limit=100)
    general_history = _sales_invoice_item_rows(item=item, limit=100)
    customer_summary = _item_purchase_summary(customer_history)

    return {
        "customer": customer,
        "item": item,
        "found_customer_specific": len(customer_history) > 0,
        "customer_specific_records": customer_history[:25],
        "customer_specific_summary": customer_summary[0] if customer_summary else None,
        "general_item_summary": _quote_rate_summary(general_history),
        "general_item_history": general_history[:25],
        "quote_rate_summary": _quote_rate_summary(general_history),
        "source": SOURCE,
    }


def get_recommendations(customer=None, items=None, limit=10):
    selected_items = []
    if items:
        if isinstance(items, str):
            selected_items = [item.strip() for item in items.split(",") if item.strip()]
        else:
            selected_items = items

    customer_items = _customer_item_codes(customer) if customer else set()
    base_items = selected_items or list(customer_items)
    recommendations = _frequently_bought_with(base_items, exclude_item_codes=customer_items, limit=limit)
    basket_items = set(selected_items)
    reminders = _repeat_purchase_reminders(customer, exclude_item_codes=basket_items, limit=limit) if customer else []

    seen = {row.get("item_code") for row in recommendations}
    for row in reminders:
        if row.get("item_code") not in seen:
            recommendations.append(row)
            seen.add(row.get("item_code"))
        if len(recommendations) >= _limit(limit):
            break

    return {
        "customer": customer,
        "items": base_items,
        "recommendations": recommendations,
        "source": SOURCE,
    }


def create_quotation(payload):
    payload = _parse_payload(payload)
    customer = _required_customer(payload)
    items = _normalized_basket_items(payload)

    doc = frappe.new_doc("Quotation")
    doc.quotation_to = payload.get("quotation_to") or "Customer"
    doc.party_name = customer
    doc.transaction_date = payload.get("transaction_date") or nowdate()
    doc.valid_till = payload.get("valid_till") or add_days(nowdate(), cint(payload.get("valid_days") or 30))
    doc.order_type = payload.get("order_type") or "Sales"
    _apply_optional_selling_fields(doc, payload)
    delivery_date = payload.get("delivery_date") or add_days(nowdate(), cint(payload.get("delivery_days") or 7))

    for item in items:
        item.setdefault("delivery_date", delivery_date)
        doc.append("items", item)

    doc.insert()
    frappe.db.commit()

    return {
        "doctype": doc.doctype,
        "name": doc.name,
        "docstatus": doc.docstatus,
        "route": _document_route(doc.doctype, doc.name),
        "source": SOURCE,
    }


def create_sales_order(payload):
    payload = _parse_payload(payload)
    customer = _required_customer(payload)
    items = _normalized_basket_items(payload)
    delivery_date = payload.get("delivery_date") or add_days(nowdate(), cint(payload.get("delivery_days") or 7))

    doc = frappe.new_doc("Sales Order")
    doc.customer = customer
    doc.transaction_date = payload.get("transaction_date") or nowdate()
    doc.delivery_date = delivery_date
    doc.order_type = payload.get("order_type") or "Sales"
    _apply_optional_selling_fields(doc, payload)

    for item in items:
        item.setdefault("delivery_date", delivery_date)
        doc.append("items", item)

    doc.insert()
    frappe.db.commit()

    return {
        "doctype": doc.doctype,
        "name": doc.name,
        "docstatus": doc.docstatus,
        "route": _document_route(doc.doctype, doc.name),
        "source": SOURCE,
    }
