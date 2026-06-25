(function () {
  window.PublicDataDashboard = window.PublicDataDashboard || {};

  function Panel({ title, children, className = "" }) {
    const panel = document.createElement("section");
    panel.className = `panel ${className}`.trim();

    const heading = document.createElement("h2");
    heading.className = "panel-title";
    heading.textContent = title;

    const body = document.createElement("div");
    body.className = "panel-body";

    if (Array.isArray(children)) {
      body.append(...children);
    } else if (children) {
      body.appendChild(children);
    }

    panel.append(heading, body);
    return panel;
  }

  window.PublicDataDashboard.Panel = Panel;
})();
