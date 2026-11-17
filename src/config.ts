import type { PublicConfig } from "./types";

export const defaultConfig: PublicConfig = {
  app_name: "INBOX",
  app_title: "Knowledge inbox",
  assistant_name: "KIN",
  assistant_title: "How can I help you today?",
  assistant_placeholder: "Ask anything about your saved content…",
  assistant_suggestions: [
    "What is my city?",
    "What do you know about me?",
    "Summarize my notes",
  ],
};
