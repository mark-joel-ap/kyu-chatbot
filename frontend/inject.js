/**
 * frontend/inject.js — embed KYU chat widget on mirrored pages.
 */
(function () {
  "use strict";

  const scriptTag = document.currentScript;
  const sameOrigin =
    window.location.protocol.startsWith("http") ? window.location.origin : null;

  const apiUrl =
    (scriptTag && scriptTag.dataset.api) ||
    window.KYU_CHAT_API ||
    sameOrigin ||
    "http://localhost:8000";

  window.KYU_CHAT_API = apiUrl;

  const baseUrl =
    scriptTag && scriptTag.src
      ? scriptTag.src.replace(/inject\.js(\?.*)?$/, "")
      : "/frontend/";

  const widgetHtmlUrl = `${baseUrl}widget.html`;
  const widgetCssUrl = `${baseUrl}css/widget.css`;
  const widgetJsUrl = `${baseUrl}widget.js`;

  function showLoadError(message) {
    console.error("[KYU Chat]", message);
    const banner = document.createElement("div");
    banner.setAttribute("role", "alert");
    banner.style.cssText =
      "position:fixed;bottom:100px;right:28px;z-index:9998;max-width:320px;" +
      "background:#ffebee;color:#b71c1c;padding:12px 16px;border-radius:8px;" +
      "font:13px/1.4 system-ui,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,0.15);";
    banner.textContent = message;
    document.body.appendChild(banner);
  }

  function loadStylesheet() {
    if (document.querySelector('link[data-kyu-widget-css]')) return;
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = widgetCssUrl;
    link.setAttribute("data-kyu-widget-css", "1");
    document.head.appendChild(link);
  }

  function loadWidgetScript() {
    const script = document.createElement("script");
    script.src = widgetJsUrl;
    script.async = false;
    script.onerror = () => showLoadError("KYU Chat script failed to load.");
    document.body.appendChild(script);
  }

  loadStylesheet();

  fetch(widgetHtmlUrl)
    .then((response) => {
      if (!response.ok) throw new Error(`Failed to load widget (${response.status})`);
      return response.text();
    })
    .then((html) => {
      const rootMatch = html.match(
        /<div id="kyu-chat-root">[\s\S]*?<\/div>\s*<!-- \/kyu-chat-root -->/
      );
      if (!rootMatch) {
        throw new Error("Widget markup not found in widget.html");
      }

      const wrapper = document.createElement("div");
      wrapper.innerHTML = rootMatch[0];
      const root = wrapper.firstElementChild;
      if (!root) throw new Error("Could not parse widget HTML");

      document.body.appendChild(root);
      loadWidgetScript();
    })
    .catch((err) => {
      showLoadError(
        "KYU Chat could not load. Ensure the backend is running."
      );
      console.warn("[KYU Chat] Load error:", err);
    });
})();
