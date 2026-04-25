"use client";

import { useEffect } from "react";
import "@n8n/chat/style.css";

const WEBHOOK_URL = "https://n8n.arleserver.cfd/webhook/codex-qdrant-chat";

export default function ChatWidget() {
  useEffect(() => {
    let cancelled = false;

    (async () => {
      const { createChat } = await import("@n8n/chat");
      if (cancelled) return;

      createChat({
        webhookUrl: WEBHOOK_URL,
        mode: "window",
        showWelcomeScreen: false,
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
    };
  }, []);

  return null;
}
