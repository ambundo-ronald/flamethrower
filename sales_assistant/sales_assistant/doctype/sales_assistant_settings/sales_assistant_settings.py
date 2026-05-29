import frappe
from frappe.model.document import Document


class SalesAssistantSettings(Document):
    def validate(self):
        if self.external_erp_url:
            self.external_erp_url = self.external_erp_url.rstrip("/")

        if self.default_source == "External Site" and not self.external_erp_url:
            frappe.throw("External ERP URL is required when External Site is the default source.")
