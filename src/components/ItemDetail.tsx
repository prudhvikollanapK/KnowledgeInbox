import { useEffect, useState } from "react";
import { api, errorMessage } from "../api";
import type { ItemDetail as Detail } from "../types";

export function ItemDetail({
  id,
  onClose,
  onChanged,
}: {
  id: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [item, setItem] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let fetching = false;
    let interval: number | undefined;
    const load = async () => {
      if (fetching) return;
      fetching = true;
      try {
        const next = await api.item(id, controller.signal);
        if (controller.signal.aborted) return;
        setItem(next);
        setError("");
        if (next.status === "ready" || next.status === "failed")
          window.clearInterval(interval);
      } catch (err) {
        if (!controller.signal.aborted) setError(errorMessage(err));
      } finally {
        fetching = false;
      }
    };
    interval = window.setInterval(() => void load(), 3000);
    void load();
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [id, revision]);

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await api.remove(id);
      onChanged();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }
  async function retry() {
    setBusy(true);
    setError("");
    try {
      const queued = await api.retry(id);
      setItem((current) => (current ? { ...current, ...queued } : null));
      setRevision((value) => value + 1);
      onChanged();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="item-detail" aria-label="Saved item details">
      <button
        type="button"
        className="text-button back-button"
        onClick={onClose}
      >
        Back to items
      </button>
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {!item ? (
        !error && <p className="muted">Loading item…</p>
      ) : (
        <>
          <h3>{item.title}</h3>
          <p className="detail-meta muted">
            {item.source_type === "note" ? "Note" : "URL"} ·{" "}
            {new Date(item.created_at).toLocaleString()} ·{" "}
            {item.status === "ready"
              ? "Ready"
              : item.status === "pending"
                ? "Queued"
                : item.status === "processing"
                  ? "Indexing"
                  : "Failed"}
          </p>
          {item.url && (
            <a
              className="detail-url"
              href={item.url}
              target="_blank"
              rel="noreferrer"
            >
              {item.url}
            </a>
          )}
          {item.error && (
            <div className="detail-error">
              <p className="error-text">{item.error}</p>
              <button type="button" onClick={retry} disabled={busy}>
                Retry indexing
              </button>
            </div>
          )}
          <div className="detail-content">
            {item.content || "Waiting for page content."}
          </div>
          <div className="detail-actions">
            {confirmDelete ? (
              <>
                <span>Delete this item?</span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setConfirmDelete(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="danger"
                  disabled={busy}
                  onClick={remove}
                >
                  {busy ? "Deleting…" : "Confirm delete"}
                </button>
              </>
            ) : (
              <button
                type="button"
                className="text-button danger"
                onClick={() => setConfirmDelete(true)}
              >
                Delete item
              </button>
            )}
          </div>
        </>
      )}
    </article>
  );
}
