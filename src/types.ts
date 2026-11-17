export type SourceType = "note" | "url";
export type Item = {
  id: string;
  title: string;
  source_type: SourceType;
  url: string | null;
  created_at: string;
  status: "pending" | "processing" | "ready" | "failed";
  error: string | null;
  preview: string;
  word_count: number;
  chunk_count: number;
};
export type ItemDetail = Item & {
  content: string;
  resolved_url: string | null;
};
export type ItemList = { items: Item[]; total: number; has_more: boolean };
export type Health = {
  status: string;
  mode: "demo" | "openai";
  ui: PublicConfig;
  warning: string | null;
  restart_required: boolean;
  api_key_configured: boolean;
  stats: {
    total: number;
    notes: number;
    urls: number;
    ready: number;
    pending: number;
    failed: number;
    chunks: number;
  };
};
export type PublicConfig = {
  app_name: string;
  app_title: string;
  assistant_name: string;
  assistant_title: string;
  assistant_placeholder: string;
  assistant_suggestions: string[];
};
export type Source = {
  citation: number;
  item_id: string;
  chunk_id: string;
  title: string;
  source_type: SourceType;
  url: string | null;
  snippet: string;
  score: number;
};
export type Answer = {
  answer: string;
  sources: Source[];
  mode: "demo" | "openai";
  insufficient_context: boolean;
  duration_ms: number;
};
