"use client";

import { useEffect, useState } from "react";
import "@n8n/chat/style.css";

const WEBHOOK_URL =
  "https://n8n.arleserver.cfd/webhook/f2d5f715-a71a-4188-8abb-d27f688a02f8/chat";

function openChatWindow(): boolean {
  const selectors = [
    ".chat-window-toggle button",
    ".chat-window-toggle",
    ".chat-toggle button",
    ".chat-toggle",
    "button[aria-label='Open chat']",
    "button[aria-label='Ava chat']",
    "button[aria-label='Ava vestlus']",
  ];

  for (const selector of selectors) {
    const el = document.querySelector<HTMLElement>(selector);
    if (el) {
      el.click();
      return true;
    }
  }

  return false;
}

export default function ChatWidget() {
  const [promptVisible, setPromptVisible] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const promptTimer = window.setTimeout(() => {
      if (!cancelled) setPromptVisible(true);
    }, 1400);

    (async () => {
      const { createChat } = await import("@n8n/chat");
      if (cancelled) return;

      const isLocalDevHost = ["localhost", "127.0.0.1"].includes(
        window.location.hostname
      );

      createChat({
        webhookUrl: WEBHOOK_URL,
        mode: "window",
        showWelcomeScreen: false,
        loadPreviousSession: !isLocalDevHost,
        defaultLanguage: "en",
        initialMessages: [
          "Tere! 👋",
          "Küsi minult Eesti talude, turgude, tootjate ja kohaliku toidu kohta. Näiteks: \"Kus saab Viimsis toorpiima?\"",
        ],
        i18n: {
          en: {
            title: "Eesti Talukaart 🇪🇪",
            subtitle: "Küsi talude, turgude ja kohaliku toidu kohta.",
            footer: "",
            getStarted: "Uus vestlus",
            inputPlaceholder: "Sinu küsimus…",
            closeButtonTooltip: "Sulge vestlus",
          },
        },
      });
    })();

    return () => {
      cancelled = true;
      window.clearTimeout(promptTimer);
    };
  }, []);

  if (!promptVisible) return null;

  return (
    <aside className="chat-prompt" aria-label="Chatbot'i soovitus">
      <button
        type="button"
        className="chat-prompt-close"
        aria-label="Peida chatbot'i soovitus"
        onClick={() => setPromptVisible(false)}
      >
        x
      </button>
      <p>Kasuta chatbot&apos;i, et leida vastuseid eesti keeles.</p>
      <button
        type="button"
        className="chat-prompt-action"
        onClick={() => {
          if (openChatWindow()) setPromptVisible(false);
        }}
      >
        Ava chatbot
      </button>
    </aside>
  );
}
