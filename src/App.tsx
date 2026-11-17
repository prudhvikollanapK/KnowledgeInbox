import { useEffect, useState } from "react";
import { useDebounce, useLibrary } from "./hooks";
import type { SourceType } from "./types";
import { AddItem } from "./components/AddItem";
import { AskPanel } from "./components/AskPanel";
import { Library } from "./components/Library";
import { defaultConfig } from "./config";

export default function App() {
  const [filter, setFilter] = useState<SourceType | "all">("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const { health, list, loading, error, refresh } = useLibrary(
    useDebounce(search),
    filter,
    page,
  );
  const ui = health?.ui || defaultConfig;
  const titleWords = ui.app_title.trim().split(/\s+/);
  const titleAccent = titleWords.pop();

  useEffect(() => {
    document.title = ui.app_title;
  }, [ui.app_title]);

  useEffect(() => {
    if (!loading && page > 0 && !list.items.length) setPage(page - 1);
  }, [list.items.length, loading, page]);

  function openItem(id: string) {
    setSelected(id);
    const heading = document.getElementById("library-title");
    heading?.focus({ preventScroll: true });
    heading?.scrollIntoView({ block: "start" });
  }

  return (
    <div className="app">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="app-header" id="top">
        <a className="wordmark" href="#top" aria-label="Inbox home">
          {ui.app_name}
        </a>
        <nav className="header-nav" aria-label="Workspace navigation">
          <a href="#library-title">Saved content</a>
          <a href="#add-title">Add content</a>
          <a
            href="#question"
            onClick={(event) => {
              event.preventDefault();
              document
                .getElementById("question")
                ?.focus({ preventScroll: true });
            }}
          >
            Ask a question
          </a>
        </nav>
        <span className="server-status">
          {error
            ? "Offline"
            : health?.restart_required
              ? "Restart needed"
              : !health
                ? "Connecting…"
                : health.mode === "demo"
                  ? "Demo mode"
                  : "OpenAI"}
          {!!health?.stats.pending && ` · ${health.stats.pending} indexing`}
        </span>
      </header>
      <main id="main">
        <div className="workspace-intro">
          <h1>
            {titleWords.length > 0 && `${titleWords.join(" ")} `}
            <span>{titleAccent}</span>
          </h1>
          <p>Save notes and links. Get answers with sources.</p>
        </div>
        {error && (
          <p className="error-message connection-error" role="alert">
            <span>{error}</span>
            <button type="button" onClick={refresh}>
              Retry
            </button>
          </p>
        )}
        <div className="workspace">
          <Library
            list={list}
            loading={loading}
            search={search}
            onSearch={(value) => {
              setSearch(value);
              setPage(0);
            }}
            type={filter}
            onType={(value) => {
              setFilter(value);
              setPage(0);
            }}
            page={page}
            onPage={setPage}
            selected={selected}
            onOpen={openItem}
            onBack={() => setSelected(null)}
            onChanged={refresh}
          />
          <div className="tools">
            <AddItem
              onSaved={() => {
                setPage(0);
                refresh();
              }}
            />
          </div>
        </div>
      </main>
      <AskPanel
        readyCount={health?.stats.ready || 0}
        pendingCount={health?.stats.pending || 0}
        failedCount={health?.stats.failed || 0}
        mode={health?.mode}
        ui={ui}
        warning={health?.warning}
        onOpen={openItem}
      />
    </div>
  );
}
