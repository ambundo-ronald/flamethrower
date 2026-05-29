import frappe

from flamethrower.services import external_erp
from flamethrower.services import local_erp


SOURCE_DEFINITIONS = [
    {
        "key": "current_site",
        "label": "Current ERPNext site",
        "type": "frappe_local",
        "status": "ready",
        "available": True,
    },
    {
        "key": "external_site",
        "label": "External ERPNext/Frappe site",
        "type": "frappe_external",
        "status": "partial",
        "available": True,
    },
]


def has_flamethrower_permission():
    return frappe.has_permission("Flamethrower Settings", "read")


def _settings():
    return frappe.get_single("Flamethrower Settings")


def _not_implemented(feature):
    frappe.throw(
        f"{feature} is planned but not implemented yet.",
        title="Flamethrower",
    )


def _selected_sources(source=None):
    settings = _settings()
    selected = source or settings.default_source or "Current Site"
    selected = selected.strip().lower().replace("_", " ")

    if selected in {"current", "current site", "local", "local frappe"}:
        if not settings.enable_current_site_source:
            frappe.throw("Current site source is disabled in Flamethrower Settings.")
        return ["current_site"]

    if selected in {"external", "external site", "external frappe"}:
        if not settings.external_erp_url or not settings.external_api_key:
            frappe.throw("External ERP source is not configured in Flamethrower Settings.")
        return ["external_site"]

    if selected == "both":
        sources = []
        if settings.enable_current_site_source:
            sources.append("current_site")
        if settings.external_erp_url and settings.external_api_key and settings.get_password("external_api_secret"):
            sources.append("external_site")
        if not sources:
            frappe.throw("No Flamethrower sources are enabled.")
        return sources

    frappe.throw(f"Unknown Flamethrower source: {source}")


def _selected_source(source=None):
    sources = _selected_sources(source)
    if len(sources) > 1:
        frappe.throw("This action requires one source. Choose Current Site or External Site.")
    return sources[0]


def _merge_results(results):
    data = []
    for result in results:
        data.extend(result.get("data") or [])
    return {
        "count": len(data),
        "data": data,
        "sources": [result.get("source") for result in results if result.get("source")],
    }


@frappe.whitelist()
def get_sources():
    settings = _settings()
    sources = []

    for source in SOURCE_DEFINITIONS:
        source = source.copy()
        if source["key"] == "current_site":
            source["enabled"] = bool(settings.enable_current_site_source)
        if source["key"] == "external_site":
            source["enabled"] = bool(
                settings.external_erp_url
                and settings.external_api_key
                and settings.get_password("external_api_secret")
            )
        sources.append(source)

    return {
        "default_source": settings.default_source,
        "sources": sources,
    }


@frappe.whitelist()
def get_settings_summary():
    settings = _settings()
    return {
        "enable_current_site_source": bool(settings.enable_current_site_source),
        "external_erp_url": settings.external_erp_url,
        "has_external_api_key": bool(settings.external_api_key),
        "has_external_api_secret": bool(settings.get_password("external_api_secret")),
        "default_source": settings.default_source,
        "external_is_read_only": True,
    }


@frappe.whitelist()
def ping():
    return {
        "status": "ok",
        "app": "flamethrower",
        "message": "Flamethrower Frappe app is installed.",
    }


@frappe.whitelist()
def search_customers(search=None, limit=20, source=None):
    results = []
    for selected in _selected_sources(source):
        if selected == "current_site":
            results.append(local_erp.search_customers(search=search, limit=limit))
        if selected == "external_site":
            results.append(external_erp.search_customers(search=search, limit=limit))
    return _merge_results(results)


@frappe.whitelist()
def get_customer_summary(customer, source=None):
    if _selected_source(source) == "current_site":
        return local_erp.get_customer_summary(customer)
    return external_erp.get_customer_summary(customer)


@frappe.whitelist()
def match_customer(customer=None, customer_name=None):
    return local_erp.match_customer(customer=customer, customer_name=customer_name)


@frappe.whitelist()
def search_items(search=None, limit=20, source=None):
    results = []
    for selected in _selected_sources(source):
        if selected == "current_site":
            results.append(local_erp.search_items(search=search, limit=limit))
        if selected == "external_site":
            results.append(external_erp.search_items(search=search, limit=limit))
    return _merge_results(results)


@frappe.whitelist()
def get_item_summary(item, source=None):
    if _selected_source(source) == "current_site":
        return local_erp.get_item_summary(item)
    _not_implemented("External item summary")


@frappe.whitelist()
def match_item(item_code=None, item_name=None):
    return local_erp.match_item(item_code=item_code, item_name=item_name)


@frappe.whitelist()
def pricing_lookup(customer, item, source=None):
    if _selected_source(source) == "current_site":
        return local_erp.pricing_lookup(customer=customer, item=item)
    return external_erp.pricing_lookup(customer=customer, item=item)


@frappe.whitelist()
def get_recommendations(customer=None, items=None, source=None, limit=10):
    if _selected_source(source) == "current_site":
        return local_erp.get_recommendations(customer=customer, items=items, limit=limit)
    return external_erp.get_recommendations(customer=customer, items=items, limit=limit)


@frappe.whitelist()
def create_quotation(payload, source=None):
    if _selected_source(source) == "current_site":
        return local_erp.create_quotation(payload)
    frappe.throw("External ERP data is read-only history. Quotations are created only in the current site.")


@frappe.whitelist()
def create_sales_order(payload, source=None):
    if _selected_source(source) == "current_site":
        return local_erp.create_sales_order(payload)
    frappe.throw("External ERP data is read-only history. Sales Orders are created only in the current site.")
