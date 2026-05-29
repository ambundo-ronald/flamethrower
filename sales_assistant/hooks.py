app_name = "sales_assistant"
app_title = "Sales Assistant"
app_publisher = "Ambundo Ronald"
app_description = "ERPNext sales assistant for customer summaries, pricing, recommendations, and quotation workflows."
app_email = "admin@example.com"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

add_to_apps_screen = [
    {
        "name": "sales_assistant",
        "logo": "/assets/sales_assistant/images/sales_assistant.svg",
        "title": "Sales Assistant",
        "route": "/app/sales-assistant",
        "has_permission": "sales_assistant.api.has_sales_assistant_permission",
    }
]
