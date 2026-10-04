// Script of summary.html and diff.html, copied inline into each page.
//
// Everything here is progressive: without script every row and every detail is visible, and the page is complete.
// With script, details start closed behind their toggle buttons and the filters can hide rows.
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");

  // Theme: automatic (follow the system), light or dark. The choice is kept in local storage when the browser
  // allows it; a page opened from a zip or with storage blocked still switches, it only forgets on reload.
  var THEMES = ["auto", "light", "dark"];
  var KEY = "inji-conformance-theme";
  function readTheme() {
    try { return localStorage.getItem(KEY) || "auto"; } catch (e) { return "auto"; }
  }
  function applyTheme(theme) {
    if (theme === "auto") { root.removeAttribute("data-theme"); } else { root.setAttribute("data-theme", theme); }
    var button = document.getElementById("theme-toggle");
    if (button) { button.textContent = "Theme: " + theme; }
  }
  var theme = readTheme();
  if (THEMES.indexOf(theme) < 0) { theme = "auto"; }
  applyTheme(theme);
  var themeButton = document.getElementById("theme-toggle");
  if (themeButton) {
    themeButton.hidden = false;
    themeButton.addEventListener("click", function () {
      theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
      try { localStorage.setItem(KEY, theme); } catch (e) { /* storage blocked: keep the choice for this view */ }
      applyTheme(theme);
    });
  }

  // Expandable module rows: a button in the module cell shows or hides the detail row below it.
  function setOpen(button, open) {
    var row = document.getElementById(button.getAttribute("aria-controls"));
    button.setAttribute("aria-expanded", open ? "true" : "false");
    if (row) { row.hidden = !open; }
  }
  var toggles = document.querySelectorAll("button.toggle");
  Array.prototype.forEach.call(toggles, function (button) {
    setOpen(button, false);
    button.addEventListener("click", function () {
      setOpen(button, button.getAttribute("aria-expanded") !== "true");
    });
  });
  // A link to #m-<component>-<module> opens that module's details.
  function openFromHash() {
    if (!location.hash) { return; }
    var target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    var button = target && target.querySelector("button.toggle");
    if (button) { setOpen(button, true); }
  }
  window.addEventListener("hashchange", openFromHash);
  openFromHash();

  // Filters: component, verdicts and free text. Each module is one <tbody> carrying data attributes.
  var filters = document.getElementById("filters");
  if (!filters) { return; }
  filters.hidden = false;
  var groups = document.querySelectorAll("tbody.module");
  var componentSelect = document.getElementById("filter-component");
  var search = document.getElementById("filter-text");
  var verdictBoxes = filters.querySelectorAll("input[name='verdict']");
  var shown = document.getElementById("shown");
  var empty = document.getElementById("no-match");

  function apply() {
    var component = componentSelect ? componentSelect.value : "";
    var text = search ? search.value.trim().toLowerCase() : "";
    var verdicts = {};
    Array.prototype.forEach.call(verdictBoxes, function (box) { verdicts[box.value] = box.checked; });
    var count = 0;
    Array.prototype.forEach.call(groups, function (group) {
      var visible = (!component || group.getAttribute("data-component") === component) &&
        verdicts[group.getAttribute("data-verdict")] !== false &&
        (!text || group.getAttribute("data-search").indexOf(text) >= 0);
      group.hidden = !visible;
      if (visible) { count += 1; }
    });
    shown.textContent = "Showing " + count + " of " + groups.length + " modules.";
    if (empty) { empty.hidden = count !== 0; }
  }
  filters.addEventListener("input", apply);
  filters.addEventListener("change", apply);
  apply();
})();
