app_name = "flamethrower"
app_title = "Flamethrower"
app_publisher = "Ambundo Ronald"
app_description = "ERPNext customer summaries, pricing, recommendations, and quotation workflows."
app_email = "admin@example.com"
app_license = "MIT"

required_apps = ["frappe", "erpnext"]

add_to_apps_screen = [
    {
        "name": "flamethrower",
        "logo": "/assets/flamethrower/images/flamethrower.svg",
        "title": "Flamethrower",
        "route": "/app/flamethrower",
        "has_permission": "flamethrower.api.has_flamethrower_permission",
    }
]
