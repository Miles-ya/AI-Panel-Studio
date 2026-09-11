import { expect, test, type Page } from "@playwright/test";

async function createReadyDiscussion(page: Page, topic: string): Promise<void> {
  await page.goto("/create");
  await page.getByLabel("讨论话题 必填").fill(topic);
  await page.getByRole("button", { name: "创建讨论" }).click();

  await expect(page.getByRole("heading", { name: topic })).toBeVisible();
  await page.getByRole("button", { name: "生成 AI 阵容" }).click();
  await expect(page.getByRole("button", { name: "确认阵容" })).toBeVisible();
  await page.getByRole("button", { name: "确认阵容" }).click();
  await expect(page.getByRole("heading", { name: "现场 Transcript" })).toBeVisible();
}

async function expectAtLeastThreeUtterances(page: Page): Promise<number> {
  await expect.poll(() => page.locator(".utterance").count(), { timeout: 15_000 }).toBeGreaterThanOrEqual(3);
  return page.locator(".utterance").count();
}

test("runs a real REST and SSE discussion from creation through its public summary", async ({ page }) => {
  const topic = "真实链路：AI 是否应参与公共决策？";

  await createReadyDiscussion(page, topic);
  await page.getByRole("button", { name: "开始讨论" }).click();

  await expectAtLeastThreeUtterances(page);
  await expect(page.getByText("这是第 3 条公开观点：应把分歧转化为可验证的行动。", { exact: true })).toBeVisible();
  await expect(page.getByText("下一步应当可验证。", { exact: true })).toBeVisible();
  await expect(page.getByText("投入节奏是否应当一次性确定？", { exact: true })).toBeVisible();
  await expect(page.getByText("讨论已收束：应以可验证的行动作为下一步。", { exact: true })).toBeVisible();
});

test("keeps separate browser pages isolated from another discussion's live events", async ({ browser }) => {
  const context = await browser.newContext();
  const pageA = await context.newPage();
  const pageB = await context.newPage();

  try {
    await createReadyDiscussion(pageA, "隔离 A：自动化与员工发展");
    await createReadyDiscussion(pageB, "隔离 B：教育公平");

    await pageA.getByRole("button", { name: "开始讨论" }).click();
    const aUtteranceCount = await expectAtLeastThreeUtterances(pageA);

    await expect(pageB.getByRole("heading", { name: "隔离 B：教育公平" })).toBeVisible();
    await expect(pageB.getByRole("button", { name: "开始讨论" })).toBeVisible();
    await expect(pageB.locator(".utterance")).toHaveCount(0);
    await expect(pageB.getByText("共识正在形成", { exact: true })).toBeVisible();
    await expect(pageB.getByText("分歧尚未显现", { exact: true })).toBeVisible();

    await pageB.getByRole("button", { name: "开始讨论" }).click();
    await expectAtLeastThreeUtterances(pageB);
    await expect(pageB.getByText("讨论已收束：应以可验证的行动作为下一步。", { exact: true })).toBeVisible();
    await expect(pageA.locator(".utterance")).toHaveCount(aUtteranceCount);
  } finally {
    await context.close();
  }
});
