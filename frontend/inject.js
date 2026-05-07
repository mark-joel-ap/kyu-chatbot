/**
 * frontend/inject.js
 * ───────────────────
 * Single-script injection loader.
 *
 * Paste ONE line before </body> in mirror/index.html to embed the widget:
 *
 *   <script src="https://your-cdn-or-path/inject.js" data-api="http://localhost:8000"></script>
 *
 * Or with a hardcoded API URL:
 *
 *   <script>window.KYU_CHAT_API="http://localhost:8000";</script>
 *   <script src="/frontend/inject.js"></script>
 *
 * This loader:
 *   1. Reads the backend API URL from data-api attribute or window.KYU_CHAT_API.
 *   2. Injects the widget CSS inline.
 *   3. Injects the widget HTML into the page.
 *   4. Boots the widget JS.
 */

(function () {
  "use strict";

  // ── Determine API URL ─────────────────────────────────────────────────────
  const scriptTag = document.currentScript;
  const apiUrl =
    (scriptTag && scriptTag.dataset.api) ||
    window.KYU_CHAT_API ||
    "http://localhost:8000";

  window.KYU_CHAT_API = apiUrl;

  // ── Inject CSS ────────────────────────────────────────────────────────────
  // In production, extract the <style> block from widget.html into widget.css
  // and load it here. For simplicity, we inline a minimal set and load the rest
  // from widget.html via fetch (if same origin) or serve widget.css separately.

  // Simple approach: fetch widget.html and inject its contents
  fetch(
    (scriptTag && scriptTag.src
      ? scriptTag.src.replace("inject.js", "widget.html")
      : "/frontend/widget.html")
  )
    .then((r) => r.text())
    .then((html) => {
      // Extract <style> block
      const styleMatch = html.match(/<style>([\s\S]*?)<\/style>/);
      if (styleMatch) {
        const style = document.createElement("style");
        style.textContent = styleMatch[1];
        document.head.appendChild(style);
      }

      // Extract widget HTML (div#kyu-chat-root + its children)
      const bodyMatch = html.match(/<div id="kyu-chat-root">([\s\S]*?)<\/div>\s*<!--\s*\/kyu/);
      const rootHtml = html.match(/<div id="kyu-chat-root">[\s\S]*?<!-- ═+\s*End of KYU Chat Widget/)?.[0];

      if (rootHtml) {
        const wrapper = document.createElement("div");
        wrapper.innerHTML = rootHtml;
        document.body.appendChild(wrapper.firstElementChild);
      }

      // Extract and execute <script> block
      const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/);
      if (scriptMatch) {
        const script = document.createElement("script");
        script.textContent = scriptMatch[1];
        document.body.appendChild(script);
      }
    })
    .catch((err) => {
      console.warn("[KYU Chat] Could not load widget:", err);
    });
})();
