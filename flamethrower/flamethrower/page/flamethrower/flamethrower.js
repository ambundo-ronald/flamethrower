frappe.pages["flamethrower"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __("Flamethrower"),
    single_column: true,
  });

  const state = {
    customerResults: [],
    itemResults: [],
    selectedCustomer: null,
    customerSummary: null,
    basket: [],
    recommendations: [],
    source: "current_site",
    customerMatch: null,
    company: frappe.defaults.get_default("company") || "",
    sellingPriceList: "",
    taxesAndCharges: "",
    deliveryDate: "",
    showAllCustomerItems: false,
    showAllTransactions: false,
  };

  const $body = $(page.body);

  const esc = (value) => frappe.utils.escape_html(value == null ? "" : String(value));
  const money = (value) => format_currency(Number(value || 0), frappe.defaults.get_default("currency"));
  const itemKey = (item) => item.item_code || item.item || item.item_name;

  function call(method, args = {}) {
    return new Promise((resolve, reject) => {
      frappe.call({
        method,
        args,
        freeze: true,
        callback(response) {
          resolve(response.message);
        },
        error(error) {
          reject(error);
        },
      });
    });
  }

  function render() {
    const customerName = state.customerSummary?.customer_name || state.selectedCustomer?.customer_name || "";
    const customerItems = state.customerSummary?.items || [];
    const visibleItems = state.showAllCustomerItems ? customerItems : customerItems.slice(0, 6);
    const transactions = state.customerSummary?.recent_transactions || {};
    const transactionRows = [
      ...(transactions.quotations || []),
      ...(transactions.sales_orders || []),
      ...(transactions.sales_invoices || []),
    ];
    const visibleTransactions = state.showAllTransactions ? transactionRows : transactionRows.slice(0, 6);

    $body.html(`
      <div class="flamethrower-page">
        <div class="sa-toolbar">
          <label>${__("Data Source")}</label>
          <select class="form-control" data-field="source">
            <option value="current_site" ${state.source === "current_site" ? "selected" : ""}>${__("Current Site")}</option>
            <option value="external_site" ${state.source === "external_site" ? "selected" : ""}>${__("External Site")}</option>
            <option value="both" ${state.source === "both" ? "selected" : ""}>${__("Both")}</option>
          </select>
          <span class="text-muted">${__("External source requires Flamethrower Settings.")}</span>
        </div>
        <div class="sa-grid">
          <section class="sa-panel sa-panel-main">
            <div class="sa-panel-head">
              <h3>${__("Customer")}</h3>
              ${customerName ? `<span class="sa-chip">${esc(customerName)}</span>` : ""}
            </div>
            <div class="sa-search-row">
              <input class="form-control" data-field="customer-search" placeholder="${__("Search customer")}" />
              <button class="btn btn-primary" data-action="search-customers">${__("Search")}</button>
            </div>
            <div class="sa-results">
              ${renderCustomerResults()}
            </div>
            ${state.customerSummary ? renderCustomerSummary(visibleItems, customerItems, visibleTransactions, transactionRows) : renderEmpty(__("No customer selected."))}
          </section>

          <section class="sa-panel">
            <div class="sa-panel-head">
              <h3>${__("Items")}</h3>
            </div>
            <div class="sa-search-row">
              <input class="form-control" data-field="item-search" placeholder="${__("Search item")}" />
              <button class="btn btn-default" data-action="search-items">${__("Search")}</button>
            </div>
            <div class="sa-results">
              ${renderItemResults()}
            </div>
          </section>

          <section class="sa-panel">
            <div class="sa-panel-head">
              <h3>${__("Basket")}</h3>
              <span class="sa-chip">${state.basket.length}</span>
            </div>
            <div class="sa-basket-settings">
              <div>
                <label>${__("Company")}</label>
                <div data-field="company"></div>
              </div>
              <div>
                <label>${__("Price List")}</label>
                <div data-field="selling-price-list"></div>
              </div>
              <div>
                <label>${__("Taxes")}</label>
                <div data-field="taxes-and-charges"></div>
              </div>
              <div>
                <label>${__("Delivery Date")}</label>
                <div data-field="delivery-date"></div>
              </div>
            </div>
            ${renderBasket()}
            <div class="sa-actions">
              <button class="btn btn-primary" data-action="create-quotation">${__("Create Quotation")}</button>
              <button class="btn btn-default" data-action="create-sales-order">${__("Create Sales Order")}</button>
            </div>
          </section>

          <section class="sa-panel sa-panel-wide">
            <div class="sa-panel-head">
              <h3>${__("Recommendations")}</h3>
              ${state.recommendations.length ? `<span class="sa-chip">${state.recommendations.length}</span>` : ""}
            </div>
            ${renderRecommendations()}
          </section>
        </div>
      </div>
    `);

    bindEvents();
    setupMatchControls();
    setupOperationalControls();
  }

  function renderEmpty(message) {
    return `<div class="sa-empty">${esc(message)}</div>`;
  }

  function renderCustomerResults() {
    if (!state.customerResults.length) return "";
    return `
      <div class="sa-list">
        ${state.customerResults
          .map(
            (row) => `
              <button class="sa-list-row" data-action="select-customer" data-customer="${esc(row.customer)}">
                <strong>${esc(row.customer_name || row.customer)}</strong>
                <span>${esc([row.source?.label, row.customer_group, row.territory].filter(Boolean).join(" - "))}</span>
              </button>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function renderCustomerSummary(visibleItems, allItems, visibleTransactions, allTransactions) {
    const summary = state.customerSummary;
    return `
      <div class="sa-metrics">
        ${metric(__("Items"), summary.item_count)}
        ${metric(__("Qty"), summary.total_qty)}
        ${metric(__("Spend"), money(summary.total_amount))}
        ${metric(__("Purchases"), summary.total_purchase_count)}
      </div>
      <div class="sa-two-col">
        ${renderContacts(summary.contacts || [])}
        ${renderAddresses(summary.addresses || [])}
      </div>
      ${renderCustomerMatch()}
      ${renderCustomerItems(visibleItems, allItems)}
      ${renderTransactions(visibleTransactions, allTransactions)}
    `;
  }

  function renderCustomerMatch() {
    if (!state.customerSummary || state.customerSummary.source?.key !== "external_site") return "";
    if (state.customerMatch?.matched) {
      return `
        <div class="sa-match sa-match-ok">
          <strong>${__("Current-site Customer")}</strong>
          <span>${esc(state.customerMatch.customer_name || state.customerMatch.customer)}</span>
        </div>
      `;
    }

    return `
      <div class="sa-match sa-match-needed">
        <div>
          <strong>${__("Match External Customer")}</strong>
          <span>${__("Choose the current-site Customer that should receive the Quotation or Sales Order.")}</span>
        </div>
        <div data-field="customer-match"></div>
      </div>
    `;
  }

  function metric(label, value) {
    return `
      <div class="sa-metric">
        <span>${esc(label)}</span>
        <strong>${esc(value)}</strong>
      </div>
    `;
  }

  function renderContacts(contacts) {
    if (!contacts.length) return renderMiniTable(__("Contacts"), []);
    const rows = contacts.map((contact) => {
      const phone = (contact.phones || []).find((row) => row.is_primary_mobile || row.is_primary_phone)?.phone || "";
      const email = (contact.emails || []).find((row) => row.is_primary)?.email_id || "";
      return [link(contact.full_name || contact.contact, contact.route), phone, email];
    });
    return renderMiniTable(__("Contacts"), rows, [__("Name"), __("Phone"), __("Email")]);
  }

  function renderAddresses(addresses) {
    if (!addresses.length) return renderMiniTable(__("Addresses"), []);
    const rows = addresses.map((address) => [
      link(address.address_title || address.address, address.route),
      address.address_type || "",
      address.display || "",
    ]);
    return renderMiniTable(__("Addresses"), rows, [__("Title"), __("Type"), __("Address")]);
  }

  function renderCustomerItems(items, allItems) {
    if (!items.length) return renderMiniTable(__("Items Bought"), []);
    const rows = items.map((item) => [
      esc(item.item_name || item.item_code),
      esc(item.total_qty),
      money(item.avg_rate),
      money(item.last_rate),
      esc(item.last_purchase_date || ""),
    ]);
    return `
      ${renderMiniTable(__("Items Bought"), rows, [__("Item"), __("Qty"), __("Avg Rate"), __("Last Rate"), __("Last Bought")])}
      ${allItems.length > 6 ? `<button class="btn btn-xs btn-default sa-see-more" data-action="toggle-customer-items">${state.showAllCustomerItems ? __("Show Less") : __("See More")}</button>` : ""}
    `;
  }

  function renderTransactions(transactions, allTransactions) {
    if (!transactions.length) return renderMiniTable(__("Recent Transactions"), []);
    const rows = transactions.map((row) => [
      esc(row.doctype),
      link(row.name, row.route),
      esc(row.date || ""),
      esc(row.status || ""),
      money(row.grand_total),
    ]);
    return `
      ${renderMiniTable(__("Recent Transactions"), rows, [__("Type"), __("Document"), __("Date"), __("Status"), __("Total")])}
      ${allTransactions.length > 6 ? `<button class="btn btn-xs btn-default sa-see-more" data-action="toggle-transactions">${state.showAllTransactions ? __("Show Less") : __("See More")}</button>` : ""}
    `;
  }

  function renderMiniTable(title, rows, headers = []) {
    if (!rows.length) {
      return `
        <div class="sa-table-block">
          <h4>${esc(title)}</h4>
          ${renderEmpty(__("No records."))}
        </div>
      `;
    }

    return `
      <div class="sa-table-block">
        <h4>${esc(title)}</h4>
        <div class="table-responsive">
          <table class="table table-bordered sa-table">
            ${headers.length ? `<thead><tr>${headers.map((header) => `<th>${esc(header)}</th>`).join("")}</tr></thead>` : ""}
            <tbody>
              ${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  function link(label, route) {
    if (!route) return esc(label);
    return `<a href="${esc(route)}">${esc(label)}</a>`;
  }

  function renderItemResults() {
    if (!state.itemResults.length) return renderEmpty(__("No items loaded."));
    return `
      <div class="sa-list">
        ${state.itemResults
          .map(
            (item) => `
              <div class="sa-result-row">
                <div>
                  <strong>${esc(item.item_name || item.item_code)}</strong>
                  <span>${esc([item.source?.label, item.item_group].filter(Boolean).join(" - "))}</span>
                </div>
                <div class="sa-row-actions">
                  <span>${money(item.last_rate || item.avg_rate)}</span>
                  <button class="btn btn-xs btn-default" data-action="add-item" data-item="${esc(item.item_code)}">${__("Add")}</button>
                </div>
              </div>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function renderBasket() {
    if (!state.basket.length) return renderEmpty(__("No items added."));
    return `
      <div class="table-responsive">
        <table class="table table-bordered sa-table">
          <thead>
            <tr>
              <th>${__("Item")}</th>
              <th>${__("Qty")}</th>
              <th>${__("Rate")}</th>
              <th>${__("Warehouse")}</th>
              <th>${__("Total")}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${state.basket
              .map(
                (line, index) => `
                  <tr>
                    <td>
                      <div>${esc(line.item_name || line.item_code)}</div>
                      ${renderLineMatch(line, index)}
                    </td>
                    <td><input class="form-control input-xs" data-action="basket-qty" data-index="${index}" type="number" min="1" value="${esc(line.qty)}" /></td>
                    <td><input class="form-control input-xs" data-action="basket-rate" data-index="${index}" type="number" min="0" step="0.01" value="${esc(line.rate)}" /></td>
                    <td><div class="sa-warehouse-control" data-field="warehouse" data-index="${index}"></div></td>
                    <td>${money(Number(line.qty || 0) * Number(line.rate || 0))}</td>
                    <td><button class="btn btn-xs btn-default" data-action="remove-line" data-index="${index}">${__("Remove")}</button></td>
                  </tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderLineMatch(line, index) {
    if (line.source?.key !== "external_site") return "";
    if (line.match?.matched) {
      return `<small class="text-muted">${__("Current-site Item")}: ${esc(line.item_code)}</small>`;
    }
    return `
      <div class="sa-line-match">
        <small>${__("Match to current-site Item")}</small>
        <div data-field="item-match" data-index="${index}"></div>
      </div>
    `;
  }

  function renderRecommendations() {
    if (!state.recommendations.length) return renderEmpty(__("No recommendations."));
    return `
      <div class="sa-recommendation-grid">
        ${state.recommendations
          .map(
            (item) => `
              <div class="sa-recommendation">
                <div>
                  <strong>${esc(item.item_name || item.item_code)}</strong>
                  <span>${esc(item.reason || "")}</span>
                  <small>${__("Suggested")}: ${money(item.suggested_rate)}</small>
                </div>
                <button class="btn btn-xs btn-default" data-action="add-recommendation" data-item="${esc(item.item_code)}">${__("Add")}</button>
              </div>
            `,
          )
          .join("")}
      </div>
    `;
  }

  function bindEvents() {
    $body.find('[data-action="search-customers"]').on("click", searchCustomers);
    $body.find('[data-field="source"]').on("change", function () {
      state.source = $(this).val();
      state.customerResults = [];
      state.itemResults = [];
      state.customerSummary = null;
      state.selectedCustomer = null;
      state.customerMatch = null;
      state.recommendations = [];
      render();
    });
    $body.find('[data-field="customer-search"]').on("keydown", (event) => {
      if (event.key === "Enter") searchCustomers();
    });
    $body.find('[data-action="select-customer"]').on("click", function () {
      loadCustomer($(this).data("customer"));
    });
    $body.find('[data-action="search-items"]').on("click", searchItems);
    $body.find('[data-field="item-search"]').on("keydown", (event) => {
      if (event.key === "Enter") searchItems();
    });
    $body.find('[data-action="add-item"]').on("click", function () {
      addItem($(this).data("item"));
    });
    $body.find('[data-action="add-recommendation"]').on("click", function () {
      addRecommendation($(this).data("item"));
    });
    $body.find('[data-action="basket-qty"]').on("change", function () {
      updateBasketLine($(this).data("index"), "qty", Number($(this).val() || 1));
    });
    $body.find('[data-action="basket-rate"]').on("change", function () {
      updateBasketLine($(this).data("index"), "rate", Number($(this).val() || 0));
    });
    $body.find('[data-action="remove-line"]').on("click", function () {
      state.basket.splice(Number($(this).data("index")), 1);
      refreshRecommendations().then(render);
    });
    $body.find('[data-action="toggle-customer-items"]').on("click", () => {
      state.showAllCustomerItems = !state.showAllCustomerItems;
      render();
    });
    $body.find('[data-action="toggle-transactions"]').on("click", () => {
      state.showAllTransactions = !state.showAllTransactions;
      render();
    });
    $body.find('[data-action="create-quotation"]').on("click", () => createDocument("quotation"));
    $body.find('[data-action="create-sales-order"]').on("click", () => createDocument("sales_order"));
  }

  function setupMatchControls() {
    const $customerMatch = $body.find('[data-field="customer-match"]');
    if ($customerMatch.length) {
      const control = frappe.ui.form.make_control({
        parent: $customerMatch,
        df: {
          fieldtype: "Link",
          options: "Customer",
          fieldname: "customer_match",
          placeholder: __("Select current-site Customer"),
          onchange() {
            const customer = control.get_value();
            if (!customer) return;
            state.customerMatch = {
              matched: true,
              customer,
              customer_name: customer,
              manually_selected: true,
            };
            render();
          },
        },
        render_input: true,
      });

      if (state.customerMatch?.customer) {
        control.set_value(state.customerMatch.customer);
      }
    }

    $body.find('[data-field="item-match"]').each(function () {
      const index = Number($(this).data("index"));
      const line = state.basket[index];
      const control = frappe.ui.form.make_control({
        parent: $(this),
        df: {
          fieldtype: "Link",
          options: "Item",
          fieldname: `item_match_${index}`,
          placeholder: __("Select current-site Item"),
          onchange() {
            const itemCode = control.get_value();
            if (!itemCode) return;
            line.item_code = itemCode;
            line.match = {
              matched: true,
              item_code: itemCode,
              item_name: itemCode,
              manually_selected: true,
            };
            render();
          },
        },
        render_input: true,
      });

      if (line.match?.item_code) {
        control.set_value(line.match.item_code);
      }
    });
  }

  function setupOperationalControls() {
    const makeLink = ({ selector, fieldname, options, placeholder, value, onchange, getQuery }) => {
      const $target = $body.find(selector);
      if (!$target.length) return;
      let control;
      control = frappe.ui.form.make_control({
        parent: $target,
        df: {
          fieldtype: "Link",
          options,
          fieldname,
          placeholder,
          get_query: getQuery,
          onchange() {
            onchange(control);
          },
        },
        render_input: true,
      });

      if (value) {
        control.set_value(value);
      }
    };

    makeLink({
      selector: '[data-field="company"]',
      fieldname: "company",
      options: "Company",
      placeholder: __("Select Company"),
      value: state.company,
      onchange(control) {
        state.company = control.get_value();
      },
    });

    makeLink({
      selector: '[data-field="selling-price-list"]',
      fieldname: "selling_price_list",
      options: "Price List",
      placeholder: __("Select Price List"),
      value: state.sellingPriceList,
      getQuery() {
        return { filters: { selling: 1 } };
      },
      onchange(control) {
        state.sellingPriceList = control.get_value();
      },
    });

    makeLink({
      selector: '[data-field="taxes-and-charges"]',
      fieldname: "taxes_and_charges",
      options: "Sales Taxes and Charges Template",
      placeholder: __("Select Tax Template"),
      value: state.taxesAndCharges,
      getQuery() {
        return state.company ? { filters: { company: state.company } } : {};
      },
      onchange(control) {
        state.taxesAndCharges = control.get_value();
      },
    });

    const $deliveryDate = $body.find('[data-field="delivery-date"]');
    if ($deliveryDate.length) {
      const control = frappe.ui.form.make_control({
        parent: $deliveryDate,
        df: {
          fieldtype: "Date",
          fieldname: "delivery_date",
          placeholder: __("Delivery Date"),
          onchange() {
            state.deliveryDate = control.get_value();
          },
        },
        render_input: true,
      });

      if (state.deliveryDate) {
        control.set_value(state.deliveryDate);
      }
    }

    $body.find('[data-field="warehouse"]').each(function () {
      const index = Number($(this).data("index"));
      const line = state.basket[index];
      const control = frappe.ui.form.make_control({
        parent: $(this),
        df: {
          fieldtype: "Link",
          options: "Warehouse",
          fieldname: `warehouse_${index}`,
          placeholder: __("Select Warehouse"),
          get_query() {
            return state.company ? { filters: { company: state.company } } : {};
          },
          onchange() {
            line.warehouse = control.get_value();
          },
        },
        render_input: true,
      });

      if (line.warehouse) {
        control.set_value(line.warehouse);
      }
    });
  }

  async function searchCustomers() {
    const search = $body.find('[data-field="customer-search"]').val();
    const result = await call("flamethrower.api.search_customers", { search, limit: 10, source: state.source });
    state.customerResults = result?.data || [];
    render();
  }

  async function loadCustomer(customer) {
    state.selectedCustomer = state.customerResults.find((row) => row.customer === customer) || { customer };
    const source = state.selectedCustomer?.source?.key || state.source;
    state.customerSummary = await call("flamethrower.api.get_customer_summary", { customer, source });
    state.customerMatch =
      source === "current_site"
        ? { matched: true, customer: state.customerSummary.customer, customer_name: state.customerSummary.customer_name }
        : await call("flamethrower.api.match_customer", {
            customer: state.customerSummary.customer,
            customer_name: state.customerSummary.customer_name,
          });
    state.showAllCustomerItems = false;
    state.showAllTransactions = false;
    await refreshRecommendations();
    render();
  }

  async function searchItems() {
    const search = $body.find('[data-field="item-search"]').val();
    const result = await call("flamethrower.api.search_items", { search, limit: 12, source: state.source });
    state.itemResults = result?.data || [];
    render();
  }

  async function addItem(itemCode) {
    const item = state.itemResults.find((row) => row.item_code === itemCode) || { item_code: itemCode };
    const existing = state.basket.find((line) => line.item_code === itemCode);
    if (existing) {
      existing.qty += 1;
      await refreshRecommendations();
      render();
      return;
    }

    const itemSource = item.source?.key || state.source;
    const itemMatch =
      itemSource === "current_site"
        ? { matched: true, item_code: item.item_code, item_name: item.item_name }
        : await call("flamethrower.api.match_item", {
            item_code: item.item_code,
            item_name: item.item_name,
          });

    let rate = item.last_rate || item.avg_rate || 0;
    if (state.customerSummary?.customer) {
      const pricing = await call("flamethrower.api.pricing_lookup", {
        customer: state.customerSummary.customer,
        item: itemCode,
        source: state.customerSummary.source?.key || state.source,
      });
      rate =
        pricing?.customer_specific_summary?.last_rate ||
        pricing?.customer_specific_summary?.avg_rate ||
        pricing?.quote_rate_summary?.most_recent_rate ||
        pricing?.quote_rate_summary?.average_rate ||
        rate;
    }

    state.basket.push({
      item_code: itemMatch?.item_code || itemCode,
      external_item_code: itemSource === "external_site" ? itemCode : undefined,
      item_name: item.item_name || itemCode,
      qty: 1,
      rate: Number(rate || 0),
      match: itemMatch,
      source: item.source,
    });
    await refreshRecommendations();
    render();
  }

  async function addRecommendation(itemCode) {
    const item = state.recommendations.find((row) => row.item_code === itemCode) || { item_code: itemCode };
    const existing = state.basket.find((line) => line.item_code === itemCode);
    if (existing) {
      existing.qty += 1;
    } else {
      const itemMatch =
        item.source?.key === "external_site"
          ? await call("flamethrower.api.match_item", {
              item_code: item.item_code,
              item_name: item.item_name,
            })
          : { matched: true, item_code: item.item_code, item_name: item.item_name };
      state.basket.push({
        item_code: itemMatch?.item_code || itemCode,
        external_item_code: item.source?.key === "external_site" ? itemCode : undefined,
        item_name: item.item_name || itemCode,
        qty: 1,
        rate: Number(item.suggested_rate || 0),
        match: itemMatch,
        source: item.source,
      });
    }
    await refreshRecommendations();
    render();
  }

  async function updateBasketLine(index, field, value) {
    state.basket[Number(index)][field] = value;
    await refreshRecommendations();
    render();
  }

  async function refreshRecommendations() {
    if (!state.customerSummary?.customer && !state.basket.length) {
      state.recommendations = [];
      return;
    }

    const result = await call("flamethrower.api.get_recommendations", {
      customer: state.customerSummary?.customer,
      items: state.basket.map(itemKey).join(","),
      limit: 10,
      source: state.customerSummary?.source?.key || state.source,
    });
    const basketItems = new Set(state.basket.map(itemKey));
    state.recommendations = (result?.recommendations || []).filter((row) => !basketItems.has(row.item_code));
  }

  async function createDocument(type) {
    if (!state.customerSummary?.customer) {
      frappe.msgprint(__("Select a customer first."));
      return;
    }
    if (!state.basket.length) {
      frappe.msgprint(__("Add at least one item."));
      return;
    }
    if (!state.customerMatch?.matched) {
      frappe.msgprint(__("Match this external customer to a current-site Customer before creating a document."));
      return;
    }
    const unmatchedLine = state.basket.find((line) => line.match && !line.match.matched);
    if (unmatchedLine) {
      frappe.msgprint(__("Match all external items to current-site Items before creating a document."));
      return;
    }
    const payload = {
      customer: state.customerMatch.customer || state.customerSummary.customer,
      items: state.basket.map((line) => ({
        item_code: line.item_code,
        qty: Number(line.qty || 1),
        rate: Number(line.rate || 0),
        warehouse: line.warehouse || undefined,
        delivery_date: state.deliveryDate || undefined,
      })),
      company: state.company || undefined,
      selling_price_list: state.sellingPriceList || undefined,
      taxes_and_charges: state.taxesAndCharges || undefined,
      delivery_date: state.deliveryDate || undefined,
      notes:
        (state.customerSummary.source?.key || state.source) === "external_site"
          ? __("Created in the current site using read-only external ERP history as context.")
          : undefined,
    };

    const method = type === "quotation" ? "flamethrower.api.create_quotation" : "flamethrower.api.create_sales_order";
    const result = await call(method, { payload: JSON.stringify(payload), source: "current_site" });
    frappe.show_alert({ message: __("{0} created", [result.name]), indicator: "green" });
    frappe.set_route("Form", result.doctype, result.name);
  }

  page.set_primary_action(__("Create Quotation"), () => createDocument("quotation"));
  page.set_secondary_action(__("Create Sales Order"), () => createDocument("sales_order"));

  render();
};
