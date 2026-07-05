(function () {
  "use strict";

  const API_BASE = window.KYU_CHAT_API || "http://localhost:8000";
  const CHAT_URL = `${API_BASE}/chat`;
  const HEALTH_URL = `${API_BASE}/health`;
  const MAX_LEN = 500;

  let isOpen = false;
  let isBusy = false;
  let hasOpened = false;
  let messageCount = 0;

  const btn = document.getElementById("kyu-chat-btn");
  const win = document.getElementById("kyu-chat-window");
  const messages = document.getElementById("kyu-messages");
  const input = document.getElementById("kyu-input");
  const sendBtn = document.getElementById("kyu-send");
  const typing = document.getElementById("kyu-typing");
  const suggs = document.getElementById("kyu-suggestions");
  const suggButtons = document.querySelectorAll(".kyu-suggestion");
  const statusDot = document.getElementById("kyu-status-dot");
  const statusText = document.getElementById("kyu-status-text");
  const charCount = document.getElementById("kyu-char-count");
  const minimizeBtn = document.getElementById("kyu-minimize-btn");

  if (!btn || !win) {
    console.error("[KYU Chat] Widget markup not found on page.");
    return;
  }

  function formatTime() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function formatSourceName(slug) {
    const name = slug
      .replace(/^kyu_ac_ug_/, "")
      .replace(/^[a-z]+_kyu_ac_ug_?/, "")
      .replace(/_/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .replace(/\b\w/g, (c) => c.toUpperCase());
    return name.length > 36 ? name.slice(0, 36) + "…" : name;
  }

  async function checkBackendHealth() {
    try {
      const res = await fetch(HEALTH_URL, { signal: AbortSignal.timeout(5000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      statusDot.style.background = "#4caf50";
      statusText.textContent = "Online";
      statusDot.title = `${data.vector_count.toLocaleString()} sources loaded`;
      return true;
    } catch {
      statusDot.style.background = "#e53935";
      statusText.textContent = "Offline";
      statusDot.title = `Cannot reach ${API_BASE}`;
      return false;
    }
  }

  checkBackendHealth();

  function toggle() {
    isOpen = !isOpen;
    btn.classList.toggle("open", isOpen);
    win.classList.toggle("visible", isOpen);

    if (isOpen) {
      if (!hasOpened) {
        hasOpened = true;
        addBotMessage(
          "Hello. I can help with Kyambogo University admissions — programmes, fees, requirements, and how to apply. What would you like to know?"
        );
      }
      setTimeout(() => input.focus(), 200);
    }
  }

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggle();
  });

  if (minimizeBtn) {
    minimizeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (isOpen) toggle();
    });
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 88) + "px";
    sendBtn.disabled = !input.value.trim() || isBusy;
    if (charCount) {
      charCount.textContent = `${input.value.length} / ${MAX_LEN}`;
    }
  });

  sendBtn.addEventListener("click", sendMessage);

  suggButtons.forEach((chip) => {
    chip.addEventListener("click", () => {
      const q = chip.dataset.q;
      if (q && !isBusy) {
        input.value = q;
        input.dispatchEvent(new Event("input"));
        sendMessage();
      }
    });
  });

  async function sendMessage() {
    const question = input.value.trim();
    if (!question || isBusy) return;

    addUserMessage(question);
    input.value = "";
    input.style.height = "auto";
    if (charCount) charCount.textContent = `0 / ${MAX_LEN}`;
    sendBtn.disabled = true;
    setBusy(true);

    if (messageCount >= 1 && suggs) {
      suggs.classList.add("hidden");
    }

    try {
      const res = await fetch(CHAT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal: AbortSignal.timeout(30000),
      });

      if (!res.ok) {
        if (res.status === 429) throw new Error("rate_limit");
        throw new Error(`http_${res.status}`);
      }

      const data = await res.json();
      addBotMessage(data.answer, data.sources || []);
    } catch (err) {
      let errMsg;
      if (err.name === "TimeoutError" || err.name === "AbortError") {
        errMsg = "The request timed out. Please try again.";
      } else if (err.message === "rate_limit") {
        errMsg = "You're sending messages too quickly. Please wait a moment.";
      } else if (err.message === "Failed to fetch" || err.name === "TypeError") {
        errMsg = `Cannot connect to the backend. Ensure the server is running at ${API_BASE}.`;
      } else {
        errMsg = "Something went wrong. Please contact admissions@kyu.ac.ug.";
      }
      addBotMessage(errMsg, [], true);
    } finally {
      setBusy(false);
      sendBtn.disabled = !input.value.trim();
    }
  }

  function addUserMessage(text) {
    messageCount++;
    const div = document.createElement("div");
    div.className = "kyu-msg user";
    div.innerHTML = `
      <div class="kyu-bubble">${escapeHtml(text)}</div>
      <span class="kyu-msg-time">${formatTime()}</span>`;
    messages.appendChild(div);
    scrollToBottom();
  }

  function addBotMessage(text, sources = [], isError = false) {
    messageCount++;
    const div = document.createElement("div");
    div.className = "kyu-msg bot";

    let sourcesHtml = "";
    if (sources && sources.length && !isError) {
      const unique = [...new Set(sources)].slice(0, 3);
      const names = unique.map((s) => escapeHtml(formatSourceName(s))).join(", ");
      sourcesHtml = `<div class="kyu-sources"><strong>Sources:</strong> ${names}</div>`;
    }

    div.innerHTML = `
      <div class="kyu-bubble${isError ? " kyu-error" : ""}">${renderMarkdown(text)}</div>
      ${sourcesHtml}
      <span class="kyu-msg-time">${formatTime()}</span>`;

    messages.appendChild(div);
    scrollToBottom();
  }

  function setBusy(busy) {
    isBusy = busy;
    typing.classList.toggle("show", busy);
    if (busy) scrollToBottom();
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      messages.scrollTop = messages.scrollHeight;
    });
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderMarkdown(text) {
    let html = escapeHtml(text);
    html = html.replace(
      /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>'
    );
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    html = html.replace(/^[-•]\s+(.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>[\s\S]*?<\/li>)+/g, (m) => `<ul>${m}</ul>`);
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  document.addEventListener("click", (e) => {
    if (isOpen && !win.contains(e.target) && !btn.contains(e.target)) {
      const fabWrap = document.getElementById("kyu-chat-fab-wrap");
      if (fabWrap && fabWrap.contains(e.target)) return;
      toggle();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && isOpen) toggle();
  });
})();
