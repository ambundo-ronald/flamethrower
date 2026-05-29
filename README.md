# Flamethrower

Flamethrower is a Frappe / ERPNext app for customer sales history, item pricing, smart recommendations, and draft Quotation or Sales Order creation.

The repository root is arranged as an installable Frappe app for Frappe Cloud and bench.

## Features

- Search ERPNext customers, contacts, addresses, accounts, and phone numbers.
- View customer summaries, recent transactions, buying patterns, and pricing history.
- Search items and build a sales basket with company, price list, taxes, delivery date, and warehouse controls.
- Create draft Quotations and Sales Orders in the current ERPNext site.
- Read customer history from an external ERPNext/Frappe site using API key and secret.
- Use external data as read-only context while creating documents only in the current site.
- Recommend repeat-purchase and frequently-bought-together items with suggested prices.

## Frappe Cloud Installation

Add this repository as a custom app in Frappe Cloud. The app name is:

```text
flamethrower
```

This app requires ERPNext because it creates and reads ERPNext selling documents.

## Bench Installation

```bash
bench get-app https://github.com/ambundo-ronald/flamethrower.git
bench --site your-site.local install-app flamethrower
bench --site your-site.local migrate
```

For local development from this folder:

```bash
bench get-app /path/to/flamethrower
bench --site your-site.local install-app flamethrower
```

## Repository Layout

```text
flamethrower/        Frappe app package
docs/                   Planning and migration notes
legacy/express_api/     Original Express JSON API prototype
legacy/vue_app/         Original Vue prototype
pyproject.toml          Python package metadata
MANIFEST.in             Package asset includes
```
