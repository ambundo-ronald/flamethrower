import frappe
from frappe.model.document import Document

from flamethrower.services.external_erp import normalize_base_url


class FlamethrowerSettings(Document):
    def validate(self):
        if self.external_erp_url:
            self.external_erp_url = normalize_base_url(self.external_erp_url)

        if self.default_source == "External Site" and not self.external_erp_url:
            frappe.throw("External ERP URL is required when External Site is the default source.")
