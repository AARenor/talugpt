// ask.js — minimal vanilla-JS fetch helper for the TaluGPT n8n webhook.
//
// Usage:
//   <div id="chat-output"></div>
//   <script src="ask.js"></script>
//   <script>askTaluGPT("Kus saab Viimsis toorpiima?")</script>

const WEBHOOK_URL = "https://n8n.arleserver.cfd/webhook/codex-qdrant-chat";

async function askTaluGPT(userMessage) {
  const out = document.getElementById("chat-output");
  if (!out) {
    console.error('Missing element with id="chat-output"');
    return;
  }
  out.textContent = "…";

  try {
    const res = await fetch(WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: userMessage }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    let data = await res.json();
    // n8n sometimes wraps a single response in an array, or returns the
    // payload as a JSON-encoded string. Normalize both.
    if (typeof data === "string") {
      try { data = JSON.parse(data); } catch { /* keep as string */ }
    }
    if (Array.isArray(data)) data = data[0] ?? {};

    let answer =
      (data && (data.answer ?? data.output ?? data.text ?? data.detail)) ??
      "";

    if (typeof answer !== "string") {
      answer = JSON.stringify(answer, null, 2);
    }
    // Defensive: if the upstream double-escaped, restore real newlines.
    answer = answer.replace(/\\n/g, "\n");

    // innerText respects "\n" as a visual line break automatically.
    out.innerText = answer || "(empty answer)";
  } catch (err) {
    out.textContent = `Sorry — couldn't reach the assistant. (${err.message})`;
    console.error(err);
  }
}

// Expose globally so plain HTML pages can call it.
if (typeof window !== "undefined") {
  window.askTaluGPT = askTaluGPT;
}
