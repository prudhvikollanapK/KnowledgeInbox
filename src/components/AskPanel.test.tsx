import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import type { Answer } from "../types";
import { AskPanel } from "./AskPanel";
import { defaultConfig } from "../config";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { query: vi.fn() },
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const answer: Answer = {
  answer: "Read every morning. [1]",
  mode: "openai",
  insufficient_context: false,
  duration_ms: 230,
  sources: [
    {
      citation: 1,
      item_id: "saved-note",
      chunk_id: "chunk-1",
      title: "Reading habit",
      source_type: "note",
      url: null,
      snippet: "Read every morning.",
      score: 0.8,
    },
  ],
};

describe("questions and sources", () => {
  it("shows clickable citations and opens the actual saved source", async () => {
    const user = userEvent.setup();
    const open = vi.fn();
    vi.mocked(api.query).mockResolvedValue(answer);
    render(<AskPanel readyCount={1} mode="openai" onOpen={open} />);
    await user.type(screen.getByRole("textbox"), "When should I read?");
    await user.click(screen.getByRole("button", { name: "Send question" }));
    expect(
      await screen.findByRole("link", { name: "View source 1" }),
    ).toHaveAttribute("href", "#source-1-1");
    await user.click(screen.getByRole("button", { name: /Reading habit/ }));
    expect(open).toHaveBeenCalledWith("saved-note");
    expect(api.query).toHaveBeenCalledWith(
      "When should I read?",
      expect.any(AbortSignal),
    );
  });

  it("disables asking until indexed content is available", async () => {
    const user = userEvent.setup();
    render(<AskPanel readyCount={0} mode="demo" onOpen={vi.fn()} />);
    await user.type(screen.getByRole("textbox"), "Anything saved?");
    expect(
      screen.getByRole("button", { name: "Send question" }),
    ).toBeDisabled();
    expect(api.query).not.toHaveBeenCalled();
  });

  it("reports query failure without losing the question", async () => {
    const user = userEvent.setup();
    vi.mocked(api.query).mockRejectedValue(
      new Error("The AI provider took too long. Please try again."),
    );
    render(<AskPanel readyCount={1} mode="openai" onOpen={vi.fn()} />);
    await user.type(screen.getByRole("textbox"), "When should I read?");
    await user.click(screen.getByRole("button", { name: "Send question" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("took too long");
    expect(screen.getByRole("textbox")).toHaveValue("When should I read?");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Send question" }),
      ).toBeEnabled(),
    );
  });

  it("uses configured assistant text and preserves drafts when collapsed", async () => {
    const user = userEvent.setup();
    render(
      <AskPanel
        readyCount={1}
        mode="openai"
        onOpen={vi.fn()}
        ui={{
          ...defaultConfig,
          assistant_name: "Atlas",
          assistant_title: "What would you like to explore?",
          assistant_placeholder: "Ask Atlas…",
          assistant_suggestions: ["When should I read?"],
        }}
      />,
    );
    expect(screen.queryByText("Atlas")).not.toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Ask Atlas…"), "A draft");
    expect(screen.getByText("Atlas")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: /What would you like to explore/ }),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Collapse chat" }));
    expect(screen.queryByText("Atlas")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("A draft");
    await user.click(screen.getByRole("textbox"));
    expect(screen.getByText("Atlas")).toBeVisible();
  });

  it("sends a suggestion and keeps citation targets unique across answers", async () => {
    const user = userEvent.setup();
    vi.mocked(api.query).mockResolvedValue(answer);
    render(
      <AskPanel
        readyCount={1}
        mode="openai"
        onOpen={vi.fn()}
        ui={{
          ...defaultConfig,
          assistant_suggestions: ["When should I read?"],
        }}
      />,
    );
    await user.click(screen.getByRole("textbox"));
    await user.click(
      screen.getByRole("button", { name: "When should I read?" }),
    );
    await screen.findByRole("link", { name: "View source 1" });
    await user.type(screen.getByRole("textbox"), "When should I read again?");
    await user.keyboard("{Enter}");
    await waitFor(() =>
      expect(
        screen.getAllByRole("link", { name: "View source 1" }),
      ).toHaveLength(2),
    );
    const links = screen.getAllByRole("link", { name: "View source 1" });
    expect(links[0].getAttribute("href")).not.toBe(
      links[1].getAttribute("href"),
    );
    expect(api.query).toHaveBeenCalledTimes(2);
  });
});
