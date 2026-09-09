import type { DiscussionStatus } from "@/types/contracts";

const scaffoldStatus: DiscussionStatus = "DRAFT";

export default function App() {
  return (
    <main className="grid min-h-screen place-items-center bg-slate-950 p-6 text-slate-50">
      <section className="w-full max-w-xl rounded-xl border border-slate-700 bg-slate-900 p-8 shadow-2xl">
        <p className="text-sm font-medium tracking-wide text-indigo-300">AI PANEL STUDIO</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">工程骨架已就绪</h1>
        <p className="mt-4 text-base leading-7 text-slate-300">
          第 1 阶段仅提供前端基础配置与 SQLite 存储层；讨论流程将在后续阶段实现。
        </p>
        <p className="mt-6 inline-flex rounded-full border border-slate-700 px-3 py-1 text-sm text-slate-300">
          当前状态：{scaffoldStatus}
        </p>
      </section>
    </main>
  );
}
