import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, errorMessage } from "../api";
import { defaultConfig } from "../config";
import type { Answer, PublicConfig } from "../types";

type Turn = {
  id: number;
  question: string;
  pending: boolean;
  answer?: Answer;
  error?: string;
};

function CitedText({ answer, turnId }: { answer: Answer; turnId: number }) {
  return (
    <div className="answer-text">
      {answer.answer.split(/(\[\d+\])/).map((part, index) => {
        const match = /^\[(\d+)\]$/.exec(part);
        const citation = match ? Number(match[1]) : null;
        return citation &&
          answer.sources.some((source) => source.citation === citation) ? (
          <a
            key={index}
            href={`#source-${turnId}-${citation}`}
            aria-label={`View source ${citation}`}
          >
            {part}
          </a>
        ) : (
          <span key={index}>{part}</span>
        );
      })}
    </div>
  );
}

function greeting() {
  const hour = new Date().getHours();
  return hour < 12
    ? "Good morning"
    : hour < 18
      ? "Good afternoon"
      : "Good evening";
}

export function AskPanel({
  readyCount,
  pendingCount = 0,
  failedCount = 0,
  mode,
  ui = defaultConfig,
  warning,
  onOpen,
}: {
  readyCount: number;
  pendingCount?: number;
  failedCount?: number;
  mode?: "demo" | "openai";
  ui?: PublicConfig;
  warning?: string | null;
  onOpen: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const controller = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const mark = ui.assistant_name.trim().slice(0, 1).toUpperCase();
  const readiness = pendingCount
    ? "Your content is being indexed. You can ask when it’s ready."
    : failedCount
      ? "Indexing failed. Open the saved item to check its error and retry."
      : "Save a note or link to get started.";

  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (body.current) body.current.scrollTop = body.current.scrollHeight;
  }, [turns, expanded]);
  useEffect(() => {
    if (!input.current) return;
    input.current.style.height = "auto";
    input.current.style.height = `${Math.min(input.current.scrollHeight, 112)}px`;
  }, [question]);

  function collapse() {
    setExpanded(false);
    input.current?.blur();
  }

  async function ask(value: string) {
    const text = value.trim();
    if (!text || busy || !readyCount) return;
    const request = new AbortController();
    controller.current?.abort();
    controller.current = request;
    const id = ++sequence.current;
    setExpanded(true);
    setBusy(true);
    setTurns((current) => [...current, { id, question: text, pending: true }]);
    let timedOut = false;
    const timeout = window.setTimeout(() => {
      timedOut = true;
      request.abort();
    }, 100_000);
    try {
      const answer = await api.query(text, request.signal);
      if (request.signal.aborted) return;
      setTurns((current) =>
        current.map((turn) =>
          turn.id === id ? { ...turn, answer, pending: false } : turn,
        ),
      );
      setQuestion("");
    } catch (err) {
      if (request.signal.aborted && !timedOut) return;
      const message = timedOut
        ? "The request timed out. Check the backend connection and try again."
        : errorMessage(err);
      setTurns((current) =>
        current.map((turn) =>
          turn.id === id ? { ...turn, error: message, pending: false } : turn,
        ),
      );
      setQuestion(text);
    } finally {
      window.clearTimeout(timeout);
      if (!request.signal.aborted || timedOut) setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(question);
  }

  return (
    <section
      className={`chat-widget ${expanded ? "is-expanded" : ""}`}
      aria-label={`Ask ${ui.assistant_name}`}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          collapse();
        }
      }}
    >
      {expanded && (
        <div className="chat-window" id="chat-window">
          <header className="chat-header">
            <span className="chat-avatar" aria-hidden="true">
              {mark}
            </span>
            <strong>{ui.assistant_name}</strong>
            <span className="chat-provider">
              {mode === "openai"
                ? "OpenAI"
                : mode === "demo"
                  ? "Demo"
                  : "Connecting…"}
            </span>
            {turns.length > 0 && (
              <button
                type="button"
                className="chat-new"
                disabled={busy}
                onClick={() => {
                  setTurns([]);
                  setQuestion("");
                  input.current?.focus();
                }}
              >
                New chat
              </button>
            )}
            <button
              type="button"
              className="chat-collapse"
              aria-label="Collapse chat"
              aria-expanded="true"
              aria-controls="chat-window"
              onClick={collapse}
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <path
                  d="m6 9 6 6 6-6"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </header>
          <div
            className={`chat-body ${turns.length ? "has-messages" : ""}`}
            ref={body}
            aria-live="polite"
            aria-busy={busy}
          >
            {!turns.length ? (
              <div className="chat-welcome">
                <span className="chat-avatar welcome-avatar" aria-hidden="true">
                  {mark}
                </span>
                <h2>
                  {greeting()}. {ui.assistant_title}
                </h2>
                <p>
                  {readyCount
                    ? "Ask about your saved notes and links."
                    : readiness}
                </p>
              </div>
            ) : (
              turns.map((turn) => (
                <article className="chat-turn" key={turn.id}>
                  <p className="chat-question">{turn.question}</p>
                  {turn.pending && (
                    <p className="chat-thinking" role="status">
                      Searching your saved content…
                    </p>
                  )}
                  {turn.error && (
                    <p className="chat-error" role="alert">
                      {turn.error}
                    </p>
                  )}
                  {turn.answer && (
                    <div className="chat-answer">
                      <CitedText answer={turn.answer} turnId={turn.id} />
                      {turn.answer.sources.length > 0 && (
                        <div className="chat-sources">
                          <h3>Sources</h3>
                          {turn.answer.sources.map((source) => (
                            <div
                              className="source"
                              id={`source-${turn.id}-${source.citation}`}
                              key={source.chunk_id}
                            >
                              <button
                                type="button"
                                className="source-title text-button"
                                onClick={() => {
                                  collapse();
                                  onOpen(source.item_id);
                                }}
                              >
                                [{source.citation}] {source.title}
                              </button>
                              <p className="source-snippet">{source.snippet}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </article>
              ))
            )}
          </div>
          {!turns.length && ui.assistant_suggestions.length > 0 && (
            <div className="chat-suggestions">
              {ui.assistant_suggestions.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  disabled={!readyCount || busy}
                  onClick={() => void ask(suggestion)}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          )}
          <p className={`chat-notice ${warning ? "has-warning" : ""}`}>
            {warning ||
              (mode === "demo"
                ? "Demo mode · answers quote matching saved passages."
                : "Answers are grounded in your saved content.")}
          </p>
        </div>
      )}
      <form onSubmit={submit} className="chat-composer">
        <label className="sr-only" htmlFor="question">
          Question
        </label>
        <textarea
          id="question"
          ref={input}
          value={question}
          rows={1}
          maxLength={2000}
          placeholder={ui.assistant_placeholder}
          disabled={busy}
          aria-controls="chat-window"
          onFocus={() => setExpanded(true)}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <button
          type="submit"
          className="chat-send"
          aria-label={busy ? "Answering question" : "Send question"}
          disabled={busy || !question.trim() || !readyCount}
        >
          <svg
            width="21"
            height="21"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M12 19V5m-5 5 5-5 5 5"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </form>
    </section>
  );
}
