import type { DiscussionDto, ParticipantDto } from "@/types/contracts";

const discussionId = "d2a4e4d6-252e-4a1d-8bbc-6c8974da7001";

export const participants: ParticipantDto[] = [
  { id: "p-mod", discussion_id: discussionId, role: "moderator", name: "林澄", profession: "科技记者", title: "商业栏目主编", stance: "优先厘清决策边界", color: "#4059D6", runtime_status: "speaking", public_focus: "正在串联可验证的行动路径" },
  { id: "p-002", discussion_id: discussionId, role: "expert", name: "周启明", profession: "组织发展顾问", title: "人力战略负责人", stance: "自动化应同步设计员工转岗机制", color: "#D97706", runtime_status: "preparing", public_focus: "正在评估转岗成本" },
  { id: "p-003", discussion_id: discussionId, role: "expert", name: "沈言", profession: "财务战略顾问", title: "企业转型顾问", stance: "应先验证可量化的投资回报", color: "#059669", runtime_status: "idle", public_focus: null },
  { id: "p-004", discussion_id: discussionId, role: "expert", name: "许宁", profession: "技术治理研究员", title: "AI 风险与合规顾问", stance: "应优先界定可审计的风险边界", color: "#C2417B", runtime_status: "idle", public_focus: null },
  { id: "p-005", discussion_id: discussionId, role: "expert", name: "韩璟", profession: "运营转型顾问", title: "共享服务负责人", stance: "从可逆流程开始试点", color: "#7C3AED", runtime_status: "idle", public_focus: null }
];

const now = "2026-09-09T08:01:10Z";
export const studioDiscussion: DiscussionDto = {
  id: discussionId, topic: "企业应如何在 AI 自动化与员工发展之间取舍？", expert_count: 4, max_public_utterances: 15, status: "RUNNING", cast_confirmed: true, cast_confirmed_at: "2026-09-09T08:00:08Z", summary: null, summary_status: "pending", error_code: null, created_at: "2026-09-09T08:00:00Z", updated_at: now, started_at: "2026-09-09T08:00:10Z", finished_at: null, participants,
  utterances: [
    { id: "u-001", discussion_id: discussionId, participant_id: "p-mod", sequence: 1, content: "今天我们讨论自动化与员工发展的平衡。先请各位界定企业真正要优化的目标。", created_at: "2026-09-09T08:00:12Z" },
    { id: "u-002", discussion_id: discussionId, participant_id: "p-002", sequence: 2, content: "若只以节省工时衡量，企业会低估转岗与复训成本。自动化应先从可逆、可衡量的流程开始。", created_at: "2026-09-09T08:01:15Z" },
    { id: "u-003", discussion_id: discussionId, participant_id: "p-003", sequence: 3, content: "我同意要可衡量，但指标不能只看成本。应把流程质量、交付速度和风险暴露一起纳入试点的基线。", created_at: "2026-09-09T08:01:48Z" },
    { id: "u-004", discussion_id: discussionId, participant_id: "p-004", sequence: 4, content: "试点还需要一个可审计边界：哪些决策可以辅助，哪些必须由人负责。边界越早明确，后续的扩张越可信。", created_at: "2026-09-09T08:02:11Z" },
    { id: "u-005", discussion_id: discussionId, participant_id: "p-mod", sequence: 5, content: "现在已有共同框架：从小范围、可衡量且责任清晰的流程开始。接下来请谈谈员工发展如何被写进这个框架。", created_at: "2026-09-09T08:02:42Z" },
    { id: "u-006", discussion_id: discussionId, participant_id: "p-002", sequence: 6, content: "培训不应是项目结束后的补救，而要与流程改造同期规划。员工需要知道新的能力会对应什么岗位与成长机会。", created_at: "2026-09-09T08:03:09Z" },
    { id: "u-007", discussion_id: discussionId, participant_id: "p-mod", sequence: 7, content: "这意味着自动化的收益账本里，既要记录节省的工时，也要记录被重新配置的人才能力。", created_at: "2026-09-09T08:03:33Z" }
  ],
  insights: [
    { id: "i-001", discussion_id: discussionId, type: "consensus", content: "自动化的评价不应只看短期降本。", active: true, created_at: now, updated_at: now }, { id: "i-002", discussion_id: discussionId, type: "consensus", content: "可逆、可衡量的流程更适合作为试点。", active: true, created_at: now, updated_at: now }, { id: "i-003", discussion_id: discussionId, type: "disagreement", content: "员工培养的投入应在试点前锁定，还是随效果逐步追加？", active: true, created_at: now, updated_at: now }, { id: "i-004", discussion_id: discussionId, type: "disagreement", content: "投资回报的优先级是否应高于治理边界的完备性？", active: true, created_at: now, updated_at: now }
  ]
};

export const homeDiscussions = [studioDiscussion, { ...studioDiscussion, id: "d-finished", topic: "AI 对教育公平的影响应如何评估？", status: "FINISHED" as const, summary: "公平既包括资源可及性，也包括学习结果与教师支持的差异。", summary_status: "succeeded" as const, updated_at: "2026-09-09T07:30:00Z" }, { ...studioDiscussion, id: "d-ready", topic: "城市是否应优先投资公共交通而非扩张道路？", status: "CAST_READY" as const, cast_confirmed: false, updated_at: "2026-09-09T07:15:00Z" }];
