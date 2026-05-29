import json
from urllib.parse import quote

import frappe
import requests
from frappe.utils import cint, flt


SOURCE = {
    "key": "external_site",
    "label": "External ERPNext/Frappe site",
    "type": "frappe_external",
}


def _limit(value, default=20, maximum=100):
    value = cint(value) or default
    return max(1, min(value, maximum))


def _round_money(value):
    return round(flt(value), 2)


def _settings():
    return frappe.get_single("Flamethrower Settings")


def _client_config():
    settings = _settings()
    base_url = (settings.external_erp_url or "").rstrip("/")
    api_key = settings.external_api_key
    api_secret = settings.get_password("external_api_secret")

    if not base_url or not api_key or not api_secret:
        frappe.throw("External ERP URL, API Key, and API Secret are required.")

    return {
        "base_url": base_url,
        "headers": {
            "Authorization": f"token {api_key}:{api_secret}",
            "Accept": "application/json",
        },
    }


def _request(path, params=None):
    config = _client_config()
    response = requests.get(
        f"{config['base_url']}{path}",
        headers=config["headers"],
        params=params or {},
        timeout=20,
    )

    if response.status_code >= 400:
        frappe.throw(
            f"External ERP request failed with status {response.status_code}: {response.text[:300]}",
            title="External ERP",
        )

    return response.json()


def _resource(doctype, fields=None, filters=None, or_filters=None, limit=20, order_by="modified desc"):
    params = {
        "fields": json.dumps(fields or ["name"]),
        "limit_page_length": _limit(limit),
        "order_by": order_by,
    }
    if filters:
        params["filters"] = json.dumps(filters)
    if or_filters:
        params["or_filters"] = json.dumps(or_filters)

    data = _request(f"/api/resource/{quote(doctype)}", params=params)
    return data.get("data") or []


def _doc(doctype, name):
    data = _request(f"/api/resource/{quote(doctype)}/{quote(name)}")
    return data.get("data") or {}


def _document_route(doctype, name):
    config = _client_config()
    return f"{config['base_url']}/app/{frappe.scrub(doctype).replace('_', '-')}/{name}"


def _like_filter(search, fields):
    if not search:
        return None
    return [[field, "like", f"%{search}%"] for field in fields]


def _source_row():
    return SOURCE.copy()


def _linked_docnames(customer, doctype):
    rows = _resource(
        "Dynamic Link",
        fields=["parent"],
        filters=[
            ["link_doctype", "=", "Customer"],
            ["link_name", "=", customer],
            ["parenttype", "=", doctype],
        ],
        limit=50,
    )
    return sorted({row.get("parent") for row in rows if row.get("parent")})


def _contact_summary(contact_name):
    contact = _doc("Contact", contact_name)
    phones = []
    emails = []

    for row in contact.get("phone_nos") or []:
        phones.append(
            {
                "phone": row.get("phone"),
                "is_primary_phone": bool(row.get("is_primary_phone")),
                "is_primary_mobile": bool(row.get("is_primary_mobile")),
            }
        )

    for row in contact.get("email_ids") or []:
        emails.append(
            {
                "email_id": row.get("email_id"),
                "is_primary": bool(row.get("is_primary")),
            }
        )

    return {
        "contact": contact.get("name"),
        "first_name": contact.get("first_name"),
        "last_name": contact.get("last_name"),
        "full_name": contact.get("full_name"),
        "designation": contact.get("designation"),
        "department": contact.get("department"),
        "phones": phones,
        "emails": emails,
        "route": _document_route("Contact", contact.get("name")),
        "source": _source_row(),
    }


def _address_summary(address_name):
    address = _doc("Address", address_name)
    lines = [
        address.get("address_line1"),
        address.get("address_line2"),
        address.get("city"),
        address.get("state"),
        address.get("country"),
    ]

    return {
        "address": address.get("name"),
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
        "route": _document_route("Address", address.get("name")),
        "source": _source_row(),
    }


def _linked_contacts(customer):
    return [_contact_summary(name) for name in _linked_docnames(customer, "Contact")]


def _linked_addresses(customer):
    return [_address_summary(name) for name in _linked_docnames(customer, "Address")]


def _recent_documents(doctype, filters, date_field, limit=5):
    rows = _resource(
        doctype,
        fields=["name", "docstatus", "status", "currency", "grand_total", date_field],
        filters=filters,
        limit=limit,
        order_by=f"{date_field} desc, modified desc",
    )

    data = []
    for row in rows:
        data.append(
            {
                "doctype": doctype,
                "name": row.get("name"),
                "date": row.get(date_field),
                "status": row.get("status"),
                "docstatus": row.get("docstatus"),
                "currency": row.get("currency"),
                "grand_total": _round_money(row.get("grand_total")),
                "route": _document_route(doctype, row.get("name")),
                "source": _source_row(),
            }
        )
    return data


def _recent_customer_transactions(customer):
    return {
        "quotations": _recent_documents("Quotation", [["party_name", "=", customer]], "transaction_date"),
        "sales_orders": _recent_documents("Sales Order", [["customer", "=", customer]], "transaction_date"),
        "sales_invoices": _recent_documents("Sales Invoice", [["customer", "=", customer]], "posting_date"),
    }


def search_customers(search=None, limit=20):
    rows = _resource(
        "Customer",
        fields=["name", "customer_name", "customer_type", "customer_group", "territory"],
        or_filters=_like_filter(search, ["name", "customer_name"]),
        limit=limit,
    )

    data = []
    for row in rows:
        data.append(
            {
                "customer_id": row.get("name"),
                "customer": row.get("name"),
                "customer_name": row.get("customer_name"),
                "customer_type": row.get("customer_type"),
                "customer_group": row.get("customer_group"),
                "territory": row.get("territory"),
                "source": _source_row(),
            }
        )

    return {"count": len(data), "data": data, "source": _source_row()}


def search_items(search=None, limit=20):
    filters = [["disabled", "=", 0]]
    search_filters = _like_filter(search, ["name", "item_code", "item_name"])

    rows = _resource(
        "Item",
        fields=["name", "item_code", "item_name", "item_group", "stock_uom"],
        filters=filters,
        or_filters=search_filters,
        limit=limit,
    )

    data = []
    for row in rows:
        data.append(
            {
                "item_id": row.get("name"),
                "item_code": row.get("item_code") or row.get("name"),
                "item_name": row.get("item_name"),
                "item_group": row.get("item_group"),
                "stock_uom": row.get("stock_uom"),
                "avg_rate": 0,
                "last_rate": 0,
                "purchase_count": 0,
                "source": _source_row(),
            }
        )

    return {"count": len(data), "data": data, "source": _source_row()}


def _invoice_docs(customer=None, limit=20):
    filters = [["docstatus", "=", 1]]
    if customer:
        filters.append(["customer", "=", customer])

    invoices = _resource(
        "Sales Invoice",
        fields=["name", "customer", "customer_name", "posting_date", "currency", "grand_total", "status"],
        filters=filters,
        limit=limit,
        order_by="posting_date desc, modified desc",
    )
    return [_doc("Sales Invoice", invoice["name"]) for invoice in invoices]


def _invoice_item_rows(customer=None, item=None, limit=20):
    rows = []
    for invoice in _invoice_docs(customer=customer, limit=limit):
        for line in invoice.get("items") or []:
            if item and item not in {line.get("item_code"), line.get("item_name")}:
                continue
            rows.append(
                {
                    "sales_invoice": invoice.get("name"),
                    "customer": invoice.get("customer"),
                    "customer_name": invoice.get("customer_name"),
                    "posting_date": invoice.get("posting_date"),
                    "currency": invoice.get("currency"),
                    "item_code": line.get("item_code"),
                    "item_name": line.get("item_name"),
                    "item_group": line.get("item_group"),
                    "uom": line.get("uom"),
                    "qty": flt(line.get("qty")),
                    "rate": flt(line.get("rate")),
                    "amount": flt(line.get("amount")),
                    "source": _source_row(),
                }
            )
    return rows


def _item_purchase_summary(rows):
    summary = {}
    for row in rows:
        key = row["item_code"] or row["item_name"]
        current = summary.setdefault(
            key,
            {
                "item_code": row["item_code"],
                "item_name": row["item_name"],
                "item_group": row["item_group"],
                "uom": row["uom"],
                "total_qty": 0,
                "total_amount": 0,
                "purchase_count": 0,
                "rates": [],
                "last_rate": 0,
                "last_purchase_date": None,
            },
        )
        current["total_qty"] += flt(row["qty"])
        current["total_amount"] += flt(row["amount"])
        current["purchase_count"] += 1
        current["rates"].append(flt(row["rate"]))
        if not current["last_purchase_date"] or row["posting_date"] > current["last_purchase_date"]:
            current["last_purchase_date"] = row["posting_date"]
            current["last_rate"] = flt(row["rate"])

    items = []
    for item in summary.values():
        rates = item.pop("rates")
        item["avg_rate"] = _round_money(sum(rates) / len(rates)) if rates else 0
        item["last_rate"] = _round_money(item["last_rate"])
        item["total_qty"] = _round_money(item["total_qty"])
        item["total_amount"] = _round_money(item["total_amount"])
        item["source"] = _source_row()
        items.append(item)
    return sorted(items, key=lambda row: row["total_amount"], reverse=True)


def get_customer_summary(customer):
    customer_doc = _doc("Customer", customer)
    rows = _invoice_item_rows(customer=customer, limit=50)
    items = _item_purchase_summary(rows)

    return {
        "customer": customer_doc.get("name") or customer,
        "customer_name": customer_doc.get("customer_name") or customer,
        "customer_type": customer_doc.get("customer_type"),
        "customer_group": customer_doc.get("customer_group"),
        "territory": customer_doc.get("territory"),
        "item_count": len(items),
        "total_qty": _round_money(sum(flt(item["total_qty"]) for item in items)),
        "total_amount": _round_money(sum(flt(item["total_amount"]) for item in items)),
        "total_purchase_count": len(rows),
        "items": items,
        "contacts": _linked_contacts(customer),
        "addresses": _linked_addresses(customer),
        "accounts": [],
        "recent_transactions": _recent_customer_transactions(customer),
        "cross_sell_suggestions": [],
        "source": _source_row(),
    }


def pricing_lookup(customer, item):
    customer_history = _invoice_item_rows(customer=customer, item=item, limit=50)
    customer_summary = _item_purchase_summary(customer_history)
    return {
        "customer": customer,
        "item": item,
        "found_customer_specific": len(customer_history) > 0,
        "customer_specific_records": customer_history[:25],
        "customer_specific_summary": customer_summary[0] if customer_summary else None,
        "general_item_summary": None,
        "general_item_history": [],
        "quote_rate_summary": None,
        "source": _source_row(),
    }


def get_recommendations(customer=None, items=None, limit=10):
    return {
        "customer": customer,
        "items": items,
        "recommendations": [],
        "source": _source_row(),
    }
