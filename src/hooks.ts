import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "./api";
import type { Health, ItemList, SourceType } from "./types";

export function useDebounce<T>(value: T, delay = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timeout = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timeout);
  }, [value, delay]);
  return debounced;
}

export function useLibrary(
  search: string,
  type: SourceType | "all",
  page: number,
) {
  const [health, setHealth] = useState<Health | null>(null);
  const [list, setList] = useState<ItemList>({
    items: [],
    total: 0,
    has_more: false,
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  const generation = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    const current = ++generation.current;
    setLoading(true);
    let fetching = false;
    const load = async () => {
      if (fetching) return;
      fetching = true;
      try {
        const [nextHealth, nextList] = await Promise.all([
          api.health(controller.signal),
          api.items(search, type, page, controller.signal),
        ]);
        if (current !== generation.current || controller.signal.aborted) return;
        setHealth(nextHealth);
        setList(nextList);
        setError("");
      } catch (err) {
        if (!controller.signal.aborted && current === generation.current)
          setError(errorMessage(err));
      } finally {
        fetching = false;
        if (!controller.signal.aborted && current === generation.current)
          setLoading(false);
      }
    };
    void load();
    // Poll without clearing existing content or flashing a loading skeleton.
    const interval = window.setInterval(() => {
      if (!document.hidden) void load();
    }, 3000);
    return () => {
      controller.abort();
      window.clearInterval(interval);
    };
  }, [search, type, page, revision]);

  return { health, list, error, loading, refresh };
}
