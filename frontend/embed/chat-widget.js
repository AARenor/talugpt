(function () {
  const script = document.currentScript;
  const apiBase = (script?.dataset.apiBase || "http://localhost:8000").replace(/\/$/, "");
  const endpoint = /\/webhook\//.test(apiBase) || /\/chat$/.test(apiBase) ? apiBase : `${apiBase}/chat`;
  const title = script?.dataset.title || "Ask your documents";
  const accent = script?.dataset.accent || "#1f6feb";

  const style = document.createElement("style");
  style.textContent = `
    .rag-widget-launcher {
      position: fixed;
      right: 20px;
      bottom: 20px;
      z-index: 2147483646;
      border: 0;
      border-radius: 999px;
      padding: 14px 18px;
      background: ${accent};
      color: #fff;
      font: 600 14px/1.2 system-ui, sans-serif;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
      cursor: pointer;
    }
    .rag-widget-shell {
      position: fixed;
      right: 20px;
      bottom: 76px;
      width: min(380px, calc(100vw - 24px));
      height: min(560px, calc(100vh - 120px));
      z-index: 2147483646;
      display: none;
      border: 1px solid #d0d7de;
      border-radius: 18px;
      overflow: hidden;
      background: #fff;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.22);
      font: 14px/1.45 system-ui, sans-serif;
    }
    .rag-widget-shell.open { display: flex; flex-direction: column; }
    .rag-widget-header {
      padding: 14px 16px;
      background: linear-gradient(135deg, ${accent}, #111827);
      color: #fff;
      font-weight: 700;
    }
    .rag-widget-messages {
      flex: 1;
      overflow-y: auto;
      padding: 14px;
      background: #f6f8fa;
    }
    .rag-widget-message {
      margin-bottom: 10px;
      max-width: 85%;
      padding: 10px 12px;
      border-radius: 14px;
      white-space: pre-wrap;
    }
    .rag-widget-message.user {
      margin-left: auto;
      background: ${accent};
      color: #fff;
    }
    .rag-widget-message.bot {
      background: #fff;
      color: #111827;
      border: 1px solid #e5e7eb;
    }
    .rag-widget-form {
      display: flex;
      gap: 8px;
      padding: 12px;
      background: #fff;
      border-top: 1px solid #e5e7eb;
    }
    .rag-widget-input {
      flex: 1;
      resize: none;
      min-height: 42px;
      max-height: 120px;
      padding: 10px 12px;
      border: 1px solid #d0d7de;
      border-radius: 12px;
      outline: none;
    }
    .rag-widget-send {
      border: 0;
      border-radius: 12px;
      padding: 0 14px;
      background: ${accent};
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
  `;
  document.head.appendChild(style);

  const launcher = document.createElement("button");
  launcher.className = "rag-widget-launcher";
  launcher.type = "button";
  launcher.textContent = title;

  const shell = document.createElement("section");
  shell.className = "rag-widget-shell";
  shell.innerHTML = `
    <div class="rag-widget-header">${title}</div>
    <div class="rag-widget-messages"></div>
    <form class="rag-widget-form">
      <textarea class="rag-widget-input" placeholder="Ask a question about your files"></textarea>
      <button class="rag-widget-send" type="submit">Send</button>
    </form>
  `;

  document.body.appendChild(launcher);
  document.body.appendChild(shell);

  const messages = shell.querySelector(".rag-widget-messages");
  const form = shell.querySelector(".rag-widget-form");
  const input = shell.querySelector(".rag-widget-input");

  function addMessage(kind, text) {
    const node = document.createElement("div");
    node.className = `rag-widget-message ${kind}`;
    node.textContent = text;
    messages.appendChild(node);
    messages.scrollTop = messages.scrollHeight;
  }

  launcher.addEventListener("click", function () {
    shell.classList.toggle("open");
    if (shell.classList.contains("open") && !messages.childElementCount) {
      addMessage("bot", "Ask anything about the documents that were ingested from Google Drive.");
    }
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const query = input.value.trim();
    if (!query) return;
    addMessage("user", query);
    input.value = "";
    addMessage("bot", "Thinking...");
    const thinking = messages.lastElementChild;

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query })
      });
      const payload = await response.json();
      const normalized = typeof payload === "string" ? safeParse(payload) : payload;
      const answer =
        normalized?.answer ||
        normalized?.output ||
        normalized?.text ||
        normalized?.detail ||
        "Request failed.";
      thinking.textContent = answer;
    } catch (error) {
      thinking.textContent = "The chat request failed. Check that the backend is running and CORS is allowed.";
    }
  });

  function safeParse(value) {
    try {
      return JSON.parse(value);
    } catch {
      return { answer: value };
    }
  }
})();
