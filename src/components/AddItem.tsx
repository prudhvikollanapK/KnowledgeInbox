import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../api";
import type { SourceType } from "../types";

export function AddItem({ onSaved }: { onSaved: () => void }) {
  const [type, setType] = useState<SourceType>("note");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const value = type === "note" ? content : url;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!value.trim() || busy) return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      await api.ingest(type, value.trim(), title.trim());
      setTitle("");
      if (type === "note") setContent("");
      else setUrl("");
      setSaved(true);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="add-title" className="add-item">
      <h2 id="add-title">Add content</h2>
      <form onSubmit={submit}>
        <fieldset className="source-types" disabled={busy}>
          <legend className="sr-only">Content type</legend>
          {(
            [
              ["note", "Note"],
              ["url", "URL"],
            ] as const
          ).map(([value, label]) => (
            <label key={value}>
              <input
                type="radio"
                name="source-type"
                value={value}
                checked={type === value}
                onChange={() => {
                  setType(value);
                  setError("");
                  setSaved(false);
                }}
              />
              {label}
            </label>
          ))}
        </fieldset>
        <label htmlFor="item-title">
          Title <span className="muted">(optional)</span>
        </label>
        <input
          id="item-title"
          placeholder="A short title"
          value={title}
          maxLength={180}
          disabled={busy}
          onChange={(event) => {
            setTitle(event.target.value);
            setSaved(false);
          }}
        />
        {type === "note" ? (
          <>
            <label htmlFor="note-content">Note</label>
            <textarea
              id="note-content"
              placeholder="Write or paste a note…"
              value={content}
              rows={4}
              maxLength={100000}
              required
              disabled={busy}
              onChange={(event) => {
                setContent(event.target.value);
                setSaved(false);
              }}
            />
          </>
        ) : (
          <>
            <label htmlFor="page-url">URL</label>
            <input
              id="page-url"
              type="url"
              value={url}
              maxLength={2048}
              required
              disabled={busy}
              placeholder="https://example.com"
              onChange={(event) => {
                setUrl(event.target.value);
                setSaved(false);
              }}
            />
          </>
        )}
        {error && (
          <p className="error-message" role="alert">
            {error}
          </p>
        )}
        <div className="form-actions">
          <button
            type="submit"
            className="primary"
            disabled={busy || !value.trim()}
          >
            {busy ? "Saving…" : "Save"}
          </button>
          {saved && (
            <span role="status" className="muted">
              Saved. Indexing in the background.
            </span>
          )}
        </div>
      </form>
    </section>
  );
}
