// Shows a spinner on the submit button so the user knows the form is working.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll("form[data-loading]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector("button[type=submit]");
      if (button) {
        var text = button.dataset.loadingText || "Please wait...";
        button.disabled = true;
        button.innerHTML =
          '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>' +
          text;
      }
    });
  });
});

// If the user presses the browser Back button, reload so buttons work again.
window.addEventListener("pageshow", function (event) {
  if (event.persisted) {
    window.location.reload();
  }
});