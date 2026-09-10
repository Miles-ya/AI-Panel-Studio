import { expect, test, type Page } from "@playwright/test";

const now = "2026-09-10T12:00:00Z";
const discussion = {
  id: "discussion-1",
  topic: "AI 是否应参与公共决策？",
  expert_count: 2,
  max_public_utterances: 15,
  status: "CAST_READY",
  cast_confirmed: true,
  cast_confirmed_at: now,
  summary: null,
  summary_status: "pending",
  error_code: null,
  created_at: now,
  updated_at: now,
  started_at: null,
  finished_at: null,
  participants: [
    { id: "moderator", discussion_id: "discussion-1", role: "moderator", name: "林岚", profession: "公共政策", title: "主持人", stance: "推动可验证的讨论", color: "#4059d6", runtime_status: "idle", public_focus: null },
    { id: "expert-1", discussion_id: "discussion-1", role: "expert", name: "周明", profession: "伦理学", title: "研究员", stance: "优先保护个人权利", color: "#087d54", runtime_status: "idle", public_focus: null },
  ],
  utterances: [],
  insights: [],
};

async function mockDiscussion(page: Page, options: { events?: string; list?: unknown; listStatus?: number; snapshot?: unknown } = {}) {
  await page.route("**/api/discussions", async (route) => {
    await route.fulfill({
      status: options.listStatus ?? 200,
      contentType: "application/json",
      body: JSON.stringify(options.list ?? { items: [] }),
    });
  });
  await page.route("**/api/discussions/discussion-1", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(options.snapshot ?? discussion) });
  });
  await page.route("**/api/discussions/discussion-1/events", async (route) => {
    await route.fulfill({ contentType: "text/event-stream", body: options.events ?? "" });
  });
}

test("pending summary hides stale fallback content and retry control", async ({ page }) => {
  await mockDiscussion(page, {
    snapshot: { ...discussion, status: "FINISHED", summary: "总结暂不可用", summary_status: "pending", finished_at: now },
  });
  await page.goto("/discussions/discussion-1");

  await expect(page.getByRole("heading", { name: "正在生成总结…" })).toBeVisible();
  await expect(page.getByText("总结暂不可用", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "重试总结" })).toHaveCount(0);
});

test("empty list offers a first-discussion action", async ({ page }) => {
  await mockDiscussion(page);
  await page.goto("/");

  await expect(page.getByRole("button", { name: "AI Panel Studio", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "发起第一场讨论" })).toBeVisible();
});

test("list failure offers a retry action", async ({ page }) => {
  await mockDiscussion(page, { listStatus: 500, list: { error: { code: "REQUEST_FAILED", message: "讨论列表加载失败。", details: {} } } });
  await page.goto("/");

  await expect(page.getByRole("button", { name: "重新加载" })).toBeVisible();
});

test("confirmed cast opens the single-column studio with the start control", async ({ page }) => {
  await mockDiscussion(page);
  await page.goto("/discussions/discussion-1");

  await expect(page.getByRole("heading", { name: "现场 Transcript" })).toBeVisible();
  await expect(page.getByRole("button", { name: "开始讨论" })).toBeVisible();
  await expect(page.getByRole("region", { name: "嘉宾席，可横向滚动查看所有嘉宾" })).toBeVisible();
  await expect(page.getByRole("button", { name: "返回讨论现场" })).toHaveCount(0);
  await expect(page.locator(".studio").evaluate((node) => Math.round(node.getBoundingClientRect().width))).resolves.toBe(1100);
  await expect(page.locator(".stage-rail").evaluate((node) => getComputedStyle(node).overflowX)).resolves.toBe("auto");
});

test("stage guest reveals their stance only on hover", async ({ page }) => {
  await mockDiscussion(page);
  await page.goto("/discussions/discussion-1");

  const guest = page.locator(".stage-guest").first();
  const stance = page.getByText("推动可验证的讨论");
  await expect(stance).toBeHidden();
  await guest.hover();
  await expect(stance).toBeVisible();
});

test("short guest lineups are centered and their stance cards stay inside the rail", async ({ page }) => {
  await mockDiscussion(page);
  await page.goto("/discussions/discussion-1");

  const rail = page.locator(".stage-rail");
  const firstGuest = page.locator(".stage-guest").first();
  await expect.poll(async () => firstGuest.evaluate((node) => node.getBoundingClientRect().left - node.parentElement!.getBoundingClientRect().left)).toBeGreaterThan(200);

  await firstGuest.hover();
  await expect.poll(async () => firstGuest.locator(".stage-stance").evaluate((node) => {
    const card = node.getBoundingClientRect();
    const bounds = node.closest(".stage-rail")!.getBoundingClientRect();
    return card.left >= bounds.left && card.right <= bounds.right;
  })).toBe(true);
  await expect.poll(async () => firstGuest.evaluate((node) => {
    const guest = node.getBoundingClientRect();
    const stance = node.querySelector(".stage-stance")!.getBoundingClientRect();
    return Math.abs((guest.left + guest.width / 2) - (stance.left + stance.width / 2)) < 1;
  })).toBe(true);
});

test("guest rail spans the viewport while the transcript remains in the studio column", async ({ page }) => {
  await mockDiscussion(page);
  await page.goto("/discussions/discussion-1");

  await expect.poll(async () => page.locator(".stage-guests").evaluate((node) => {
    const bounds = node.getBoundingClientRect();
    return Math.abs(bounds.left) < 1 && Math.abs(bounds.width - window.innerWidth) < 1;
  })).toBe(true);
  await expect(page.locator(".transcript").evaluate((node) => node.getBoundingClientRect().width)).resolves.toBe(1100);
});

test("stage guest does not provide a clickable stance control", async ({ page }) => {
  await mockDiscussion(page);
  await page.goto("/discussions/discussion-1");

  const guest = page.locator(".stage-guest").first();
  await expect(guest.getByRole("button")).toHaveCount(0);
});

test("SSE insights render in the studio and a lost connection is announced", async ({ page }) => {
  const insights = [
    { id: "insight-1", discussion_id: "discussion-1", type: "consensus", content: "透明度是最低共识。", active: true, created_at: now, updated_at: now },
    { id: "insight-2", discussion_id: "discussion-1", type: "disagreement", content: "责任归属仍有分歧。", active: true, created_at: now, updated_at: now },
  ];
  await mockDiscussion(page, { events: `event: insights.updated\ndata: ${JSON.stringify({ discussion_id: "discussion-1", insights })}\n\n` });
  await page.goto("/discussions/discussion-1");

  await expect(page.getByText("透明度是最低共识。")).toBeVisible();
  await expect(page.getByText("责任归属仍有分歧。")).toBeVisible();
  await expect(page.getByText("正在连接")).toBeVisible();
});
