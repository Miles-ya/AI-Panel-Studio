from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Discussion, Participant


SEED_DISCUSSIONS = (
    ("00000000-0000-4000-8000-000000000001", "企业应如何在 AI 自动化与员工发展之间取舍？"),
    ("00000000-0000-4000-8000-000000000002", "AI 对教育公平的影响应如何评估？"),
    ("00000000-0000-4000-8000-000000000003", "城市是否应优先投资公共交通而非扩张道路？"),
    ("00000000-0000-4000-8000-000000000004", "生成式 AI 如何改变内容创作者的职业路径？"),
    ("00000000-0000-4000-8000-000000000005", "企业减碳目标与短期盈利压力如何协调？"),
)

CAST_TEMPLATE = (
    ("moderator", "林澄", "科技记者", "商业栏目主编", "优先厘清讨论中的决策边界", "#2563EB"),
    ("expert", "周启明", "组织发展顾问", "人力战略负责人", "自动化应同步设计员工转岗机制", "#F59E0B"),
    ("expert", "沈言", "财务战略顾问", "企业转型顾问", "应先验证可量化的投资回报", "#10B981"),
    ("expert", "许宁", "技术治理研究员", "AI 风险与合规顾问", "应优先界定可审计的风险边界", "#EC4899"),
    ("expert", "韩璟", "运营转型顾问", "共享服务负责人", "从可逆流程开始试点", "#8B5CF6"),
)


def seed_presets(session: Session) -> None:
    """Insert only missing fixed presets; never overwrite existing records."""
    now = datetime.now(UTC)
    for index, (discussion_id, topic) in enumerate(SEED_DISCUSSIONS, start=1):
        if session.get(Discussion, discussion_id) is None:
            session.add(
                Discussion(
                    id=discussion_id,
                    topic=topic,
                    expert_count=4,
                    max_public_utterances=15,
                    status="CAST_READY",
                    cast_confirmed=False,
                    summary_status="pending",
                    created_at=now,
                    updated_at=now,
                )
            )
        for participant_index, participant in enumerate(CAST_TEMPLATE, start=1):
            participant_id = f"00000000-0000-4000-900{index}-{participant_index:012d}"
            if session.get(Participant, participant_id) is not None:
                continue
            role, name, profession, title, stance, color = participant
            session.add(
                Participant(
                    id=participant_id,
                    discussion_id=discussion_id,
                    role=role,
                    name=name,
                    profession=profession,
                    title=title,
                    stance=stance,
                    color=color,
                    runtime_status="idle",
                    created_at=now,
                )
            )
    session.commit()
