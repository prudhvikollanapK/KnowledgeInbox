
import type {
  Answer,
  Health,
  Item,
  ItemDetail,
  ItemList,
  SourceType,
} from "./types";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || ""
).replace(/\/$/, "");


async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);

  if (options.body !== undefined && options.body !== null) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}/api${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const error = payload?.error;
    const fieldMessage = error?.fields?.[0]?.message;

    throw new Error(
      fieldMessage ||
        error?.message ||
        `Request failed (${response.status}). Please try again.`,
    );
  }

  return response.status === 204 ? (undefined as T) : response.json();
}


export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", { signal }),
  items: (
    search: string,
    type: SourceType | "all",
    page: number,
    signal?: AbortSignal,
  ) => {
    const params = new URLSearchParams({
      search,
      limit: "12",
      offset: String(page * 12),
    });
    if (type !== "all") params.set("source_type", type);
    return request<ItemList>(`/items?${params}`, { signal });
  },
  item: (id: string, signal?: AbortSignal) =>
    request<ItemDetail>(`/items/${id}`, { signal }),
  ingest: (source_type: SourceType, content: string, title = "") =>
    request<Item>("/ingest", {
      method: "POST",
      body: JSON.stringify({ source_type, content, title }),
    }),
  remove: (id: string) => request<void>(`/items/${id}`, { method: "DELETE" }),
  retry: (id: string) =>
    request<Item>(`/items/${id}/retry`, { method: "POST" }),
  query: (question: string, signal?: AbortSignal) =>
    request<Answer>("/query", {
      method: "POST",
      body: JSON.stringify({ question, top_k: 5 }),
      signal,
    }),
};

export function errorMessage(error: unknown): string {
  if (error instanceof TypeError)
    return "Can’t reach the server. Check that the backend is running and try again.";
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}
