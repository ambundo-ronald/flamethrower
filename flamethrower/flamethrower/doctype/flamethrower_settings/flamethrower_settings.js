frappe.ui.form.on("Flamethrower Settings", {
  refresh(frm) {
    frm.add_custom_button(__("Test Current Site"), () => {
      frappe.call({
        method: "flamethrower.api.ping",
        callback(response) {
          frappe.msgprint(response.message.message || __("Flamethrower is reachable."));
        },
      });
    });
  },
});
