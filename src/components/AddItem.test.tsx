import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { AddItem } from "./AddItem";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  api: { ingest: vi.fn() },
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("content ingestion", () => {
  it("submits a URL as a URL and keeps optional title separate", async () => {
    const user = userEvent.setup();
    const saved = vi.fn();
    vi.mocked(api.ingest).mockResolvedValue(
      {} as Awaited<ReturnType<typeof api.ingest>>,
    );
    render(<AddItem onSaved={saved} />);
    await user.click(screen.getByRole("radio", { name: "URL" }));
    await user.type(screen.getByLabelText("Title (optional)"), "A useful page");
    await user.type(
      screen.getByRole("textbox", { name: "URL" }),
      "https://example.com/article",
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(api.ingest).toHaveBeenCalledWith(
      "url",
      "https://example.com/article",
      "A useful page",
    );
    expect(saved).toHaveBeenCalledOnce();
  });

  it("preserves the note and shows an actionable error when saving fails", async () => {
    const user = userEvent.setup();
    vi.mocked(api.ingest).mockRejectedValue(
      new Error("The inbox is busy. Try again shortly."),
    );
    render(<AddItem onSaved={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Note" }), {
      target: { value: "Do not lose this thought." },
    });
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The inbox is busy.",
    );
    expect(screen.getByRole("textbox", { name: "Note" })).toHaveValue(
      "Do not lose this thought.",
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save" })).toBeEnabled(),
    );
  });
});
