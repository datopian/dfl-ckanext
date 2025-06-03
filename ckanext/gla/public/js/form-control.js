function setFormValidationRules(forms, options) {
  forms.forEach((form) => {
    if (form) {
      const validator = new JustValidate(form, {
        validateBeforeSubmitting: true,
      });

      const fields = form.querySelectorAll("input, textarea, select");

      fields.forEach((field) => {
        const rules = [];
        if (!field.id) {
          field.id = `field-${Math.random().toString(36).slice(2, 11)}`;
        }
        const errorContainerId = `${field.id}-error`;

        let errorContainer = document.getElementById(errorContainerId);
        if (!errorContainer) {
          errorContainer = document.createElement("div");
          errorContainer.id = errorContainerId;
          errorContainer.className = "error-message";
          errorContainer.setAttribute("aria-live", "polite");
          errorContainer.setAttribute("role", "alert");

          field.insertAdjacentElement("afterend", errorContainer);
        }

        field.setAttribute("aria-describedby", errorContainerId);

        if (field.hasAttribute("required")) {
          rules.push({
            rule: "required",
            errorMessage:
              field.getAttribute("data-error-required") || "Required field",
          });
        }

        if (field.type === "email") {
          rules.push({
            rule: "email",
            errorMessage:
              field.getAttribute("data-error-email") || "Invalid email address",
          });
        }

        if (field.hasAttribute("minlength")) {
          rules.push({
            rule: "minLength",
            value: parseInt(field.getAttribute("minlength")),
            errorMessage:
              field.getAttribute("data-error-minlength") || "Too short",
          });
        }

        if (field.hasAttribute("maxlength")) {
          rules.push({
            rule: "maxLength",
            value: parseInt(field.getAttribute("maxlength")),
            errorMessage:
              field.getAttribute("data-error-maxlength") || "Too long",
          });
        }
        if (rules.length > 0) {
          validator.addField(`#${field.id}`, rules, {
            errorsContainer: `#${errorContainerId}`,
          });
        }
      });

      validator.onFail((fields) => {
        const firstInvalid = form.querySelector(".just-validate-error-field");
        if (firstInvalid) firstInvalid.focus();
      });

      validator.onSuccess((e) => {
        e.preventDefault();
        if (options?.onSuccess) {
          options.onSuccess({
            form,
            event: e,
          });
        }
        return false;
      });
    }
  });
}

document.addEventListener("DOMContentLoaded", function () {
  setFormValidationRules(document.querySelectorAll("form.form-validate"), {
    onSuccess: ({ form }) => {
      form?.submit();
    },
  });
});
