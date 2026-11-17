import { expect, test } from "@playwright/test";

test.beforeEach(async ({ request }) => {
  const response = await request.get("/api/items?limit=100");
  for (const item of (await response.json()).items)
    await request.delete(`/api/items/${item.id}`);
});

test("saved items, cited answers, inline detail, and deletion", async ({
  page,
  request,
}, testInfo) => {
  const notes = [
    {
      title: "Meeting notes",
      content:
        "Prepare a meeting agenda in advance. Share a short agenda and context before each meeting. End with action owners and deadlines.",
    },
    {
      title: "Reading",
      content: "Read for ten minutes after breakfast each day.",
    },
    {
      title: "Project plan",
      content: "The first release is scheduled for Friday.",
    },
  ];
  for (const note of notes) {
    const saved = await request.post("/api/ingest", {
      data: { source_type: "note", ...note },
    });
    expect(saved.status()).toBe(202);
  }
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Knowledge inbox",
  );
  await expect(page.getByText("Ready", { exact: true })).toHaveCount(3);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".chat-window")).toHaveCount(0);
  await page.getByRole("textbox", { name: "Question" }).focus();
  await expect(page.locator(".chat-window")).toBeVisible();
  await expect(page.locator(".chat-header strong")).toHaveText("KIN");
  await page.screenshot({
    path: `artifacts/${testInfo.project.name}-chat-welcome.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Collapse chat" }).click();
  await page.screenshot({
    path: `artifacts/${testInfo.project.name}-library.png`,
    fullPage: true,
  });

  await page
    .getByRole("textbox", { name: "Question" })
    .fill("How do I prepare an agenda for a meeting?");
  await page
    .getByRole("button", { name: "Send question", exact: true })
    .click();
  await expect(page.locator(".answer-text")).toContainText("relevant passages");
  await expect(
    page.getByRole("link", { name: /View source/ }).first(),
  ).toBeVisible();
  await page.screenshot({
    path: `artifacts/${testInfo.project.name}-answer.png`,
    fullPage: true,
  });

  await page.getByRole("button", { name: /\[1\] Meeting notes/ }).click();
  await expect(
    page.getByRole("article", { name: "Saved item details" }),
  ).toBeVisible();
  await expect(page.locator(".detail-content")).toContainText(
    "Share a short agenda",
  );
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Delete item", exact: true }).click();
  await page
    .getByRole("button", { name: "Confirm delete", exact: true })
    .click();
  await expect(page.locator(".item-count")).toHaveText("(2)");
  await expect(page.locator(".item-row")).toHaveCount(2);
  await page
    .getByRole("combobox", { name: "Filter by type" })
    .selectOption("url");
  await expect(page.getByText("No matching items.")).toBeVisible();
  await page
    .getByRole("combobox", { name: "Filter by type" })
    .selectOption("all");
  await page
    .getByRole("searchbox", { name: "Search saved items" })
    .fill("Reading");
  await expect(page.locator(".item-row")).toHaveCount(1);
  await expect(page.locator(".item-title")).toHaveText("Reading");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(pageErrors).toEqual([]);
});

test("inline saving and unsafe URL validation preserve input", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Send question", exact: true }),
  ).toBeDisabled();
  await page.getByLabel("Title (optional)").fill("A note from the browser");
  await page
    .getByRole("textbox", { name: "Note", exact: true })
    .fill("Useful knowledge can be saved directly from the page.");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.locator(".item-row")).toContainText(
    "A note from the browser",
  );
  await expect(
    page.getByRole("textbox", { name: "Note", exact: true }),
  ).toHaveValue("");
  await page.getByRole("radio", { name: "URL" }).check();
  await page
    .getByRole("textbox", { name: "URL", exact: true })
    .fill("http://127.0.0.1/");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("blocked");
  await expect(
    page.getByRole("textbox", { name: "URL", exact: true }),
  ).toHaveValue("http://127.0.0.1/");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("chat suggestions answer a short note using its title", async ({
  page,
  request,
}) => {
  await request.post("/api/ingest", {
    data: { source_type: "note", title: "city", content: "vizag" },
  });
  await page.goto("/");
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Question" }).focus();
  await page
    .getByRole("button", { name: "What is my city?", exact: true })
    .click();
  await expect(page.locator(".answer-text")).toContainText("vizag");
  await expect(page.getByRole("link", { name: "View source 1" })).toBeVisible();
  await page.getByRole("button", { name: "Collapse chat" }).click();
  await expect(page.locator(".chat-window")).toHaveCount(0);
  await page.getByRole("textbox", { name: "Question" }).focus();
  await expect(page.locator(".answer-text")).toContainText("vizag");
});
