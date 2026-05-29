frappe.ui.form.on("Sales Assistant Settings", {
  refresh(frm) {
    frm.add_custom_button(__("Test Current Site"), () => {
      frappe.call({
        method: "sales_assistant.api.ping",
        callback(response) {
          frappe.msgprint(response.message.message || __("Sales Assistant is reachable."));
        },
      });
    });
  },
});
