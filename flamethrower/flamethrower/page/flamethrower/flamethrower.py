import frappe


@frappe.whitelist()
def get_context():
    return {
        "settings": frappe.call("flamethrower.api.get_settings_summary"),
        "sources": frappe.call("flamethrower.api.get_sources"),
    }
