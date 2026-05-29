import frappe


@frappe.whitelist()
def get_context():
    return {
        "settings": frappe.call("sales_assistant.api.get_settings_summary"),
        "sources": frappe.call("sales_assistant.api.get_sources"),
    }
