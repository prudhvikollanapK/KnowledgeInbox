import type { Item, ItemList, SourceType } from "../types";
import { ItemDetail } from "./ItemDetail";

export function ItemStatus({ item }: { item: Item }) {
  const labels = {
    ready: "Ready",
    pending: "Queued",
    processing: "Indexing",
    failed: "Failed",
  };
  return (
    <span className={`item-status ${item.status}`}>{labels[item.status]}</span>
  );
}

export function Library({
  list,
  loading,
  search,
  onSearch,
  type,
  onType,
  page,
  onPage,
  selected,
  onOpen,
  onBack,
  onChanged,
}: {
  list: ItemList;
  loading: boolean;
  search: string;
  onSearch: (value: string) => void;
  type: SourceType | "all";
  onType: (value: SourceType | "all") => void;
  page: number;
  onPage: (page: number) => void;
  selected: string | null;
  onOpen: (id: string) => void;
  onBack: () => void;
  onChanged: () => void;
}) {
  return (
    <section className="library" aria-labelledby="library-title">
      <h2 id="library-title" tabIndex={-1}>
        Saved items <span className="item-count">({list.total})</span>
      </h2>
      {selected ? (
        <ItemDetail
          key={selected}
          id={selected}
          onClose={onBack}
          onChanged={onChanged}
        />
      ) : (
        <>
          <div className="library-toolbar">
            <label className="sr-only" htmlFor="library-search">
              Search saved items
            </label>
            <input
              id="library-search"
              type="search"
              value={search}
              maxLength={200}
              placeholder="Search items"
              onChange={(event) => onSearch(event.target.value)}
            />
            <label className="sr-only" htmlFor="source-filter">
              Filter by type
            </label>
            <select
              id="source-filter"
              value={type}
              onChange={(event) =>
                onType(event.target.value as SourceType | "all")
              }
            >
              <option value="all">All types</option>
              <option value="note">Notes</option>
              <option value="url">URLs</option>
            </select>
          </div>
          {!list.items.length ? (
            <p className="empty-list muted">
              {loading
                ? "Loading items…"
                : search || type !== "all"
                  ? "No matching items."
                  : "No saved items yet."}
            </p>
          ) : (
            <ul className="item-list">
              {list.items.map((item) => (
                <li className="item-row" key={item.id}>
                  <button
                    type="button"
                    className="item-title"
                    onClick={() => onOpen(item.id)}
                  >
                    {item.title}
                  </button>
                  <div className="item-meta">
                    <span>{item.source_type === "note" ? "Note" : "URL"}</span>
                    <span>·</span>
                    <time dateTime={item.created_at}>
                      {new Date(item.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                      })}
                    </time>
                    <span>·</span>
                    <ItemStatus item={item} />
                  </div>
                  <p
                    className={`item-preview ${item.error ? "error-text" : ""}`}
                  >
                    {item.error || item.preview || "Fetching page content…"}
                  </p>
                </li>
              ))}
            </ul>
          )}
          {(page > 0 || list.has_more) && (
            <div className="pagination">
              <span className="muted">
                {page * 12 + 1}–{Math.min((page + 1) * 12, list.total)} of{" "}
                {list.total}
              </span>
              <div>
                <button
                  type="button"
                  disabled={page === 0}
                  onClick={() => onPage(page - 1)}
                >
                  Previous
                </button>
                <button
                  type="button"
                  disabled={!list.has_more}
                  onClick={() => onPage(page + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
