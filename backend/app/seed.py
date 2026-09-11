from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Discussion, Insight, Participant, Utterance


PALETTE = ("#2563EB", "#F59E0B", "#10B981", "#EC4899", "#8B5CF6")

# Each preset is a finished, directly observable studio session: topic, summary,
# moderator/expert roster, four public utterances, consensus, and disagreement.
SAMPLE_DISCUSSIONS = (
    (
        "企业应如何在 AI 自动化与员工发展之间取舍？",
        "讨论认为，自动化不应只以降本衡量；企业应从可逆流程试点，并把员工转岗与能力建设纳入同一套验收指标。",
        (
            ("林澄", "科技记者", "圆桌主持人", "先厘清自动化决策的边界"),
            ("周启明", "组织发展顾问", "人力战略负责人", "自动化必须同步设计员工转岗"),
            ("沈言", "财务战略顾问", "企业转型顾问", "先验证可量化的投资回报"),
            ("许宁", "技术治理研究员", "AI 风险与合规顾问", "优先界定可审计的风险边界"),
            ("韩璟", "运营转型顾问", "共享服务负责人", "从可逆流程开始试点"),
        ),
        (
            (0, "今天不把自动化简单等同于裁员，而是讨论效率收益如何与员工发展一起被衡量。"),
            (1, "若岗位变化没有转岗路径，短期效率会转化为组织信任成本；员工参与设计应当从试点开始。"),
            (2, "转型仍需财务纪律。应先在流程稳定、收益可测的环节设定投资回收和质量指标。"),
            (0, "共识是从可逆试点开始，并同时公布业务收益、服务质量和人员转岗三类指标。"),
        ),
        ("自动化试点应同时衡量业务、服务与人才结果。", "转岗投入应由中心统一承担还是由业务单元承担？"),
    ),
    (
        "AI 对教育公平的影响应如何评估？",
        "讨论认为，AI 能扩大高质量学习支持的可及性，但前提是设备、数据保护和教师支持同时到位；评估不能只看使用率。",
        (
            ("程岚", "教育记者", "教育议题主持人", "区分可及性与真实学习收益"),
            ("苏禾", "教育技术研究者", "学习科学副教授", "以学习成效而非使用时长评估"),
            ("罗颖", "乡村学校校长", "基础教育实践者", "设备与教师支持决定实际可及性"),
            ("顾言", "数据隐私律师", "未成年人数据保护顾问", "未成年人数据必须最小化收集"),
            ("魏然", "课程设计师", "数字课程负责人", "工具要服从课程目标"),
        ),
        (
            (0, "教育公平不能只问学生能否登录，还要问他们是否获得了稳定、有效且安全的学习支持。"),
            (1, "应比较学习迁移和持续进步，而不是以互动次数或在线时长替代学习成效。"),
            (2, "偏远学校最缺的常常不是一个工具，而是网络、设备维护和能把工具带入课堂的教师。"),
            (0, "因此，试点评估应同时记录学习结果、资源可达性与隐私保护，不让任何一个指标独自决定结论。"),
        ),
        ("教育 AI 的成效评估应包含学习结果、可及性与隐私。", "资源应优先投入通用设备网络，还是投入个性化 AI 服务？"),
    ),
    (
        "城市是否应优先投资公共交通而非扩张道路？",
        "讨论认为，公共交通优先并不意味着停止道路维护，而是应把有限新增投资优先投向高容量、可达性更好的出行方式。",
        (
            ("顾远", "城市观察者", "公共事务主持人", "从居民可达性而非车流量切入"),
            ("陆川", "交通规划师", "城市交通总工", "新增容量应服务更多人而非更多车"),
            ("陈雨", "物流经济学者", "供应链研究员", "保留货运与应急道路韧性"),
            ("唐宁", "社区组织者", "无障碍出行倡导者", "换乘成本决定弱势群体是否受益"),
            ("何卓", "财政分析师", "公共投资顾问", "用全生命周期成本比较方案"),
        ),
        (
            (0, "今天的关键不是道路或公交二选一，而是新增投资怎样让更多居民获得可靠出行。"),
            (1, "高频公交和轨道在走廊上的单位空间载客量更高，能缓解拥堵也能扩大就业可达范围。"),
            (2, "道路维护、货运和紧急服务不能被忽略，投资排序需要保留城市物流的基本韧性。"),
            (0, "可把新增扩张预算优先用于公共交通，同时以可达性、准点率和货运保障共同验收。"),
        ),
        ("新增投资应以居民可达性和全生命周期成本评估。", "有限预算中，轨道建设与快速公交应如何排序？"),
    ),
    (
        "生成式 AI 如何改变内容创作者的职业路径？",
        "讨论认为，生成式 AI 会压缩重复制作环节，但创作者的差异化会更集中于选题判断、可信关系、审美取舍和对结果的责任。",
        (
            ("叶青", "文化记者", "创作者圆桌主持人", "讨论效率工具与创作主体性"),
            ("姜然", "独立导演", "影像创作者", "保留人的选题和审美判断"),
            ("白薇", "平台策略研究员", "创作者增长顾问", "关注分发规则与收益分配"),
            ("宋野", "版权律师", "数字内容法律顾问", "素材来源和署名责任需清晰"),
            ("安可", "教育产品经理", "创作者培训负责人", "把 AI 素养转为可迁移能力"),
        ),
        (
            (0, "生成式 AI 已经改变制作速度，但职业路径的变化不应只用替代或不替代来描述。"),
            (1, "工具能生成素材，却不能替创作者决定什么值得拍、应该舍弃什么，以及如何承担表达后果。"),
            (2, "平台若只奖励低成本高频内容，会放大同质化；收益和分发规则会直接影响创作生态。"),
            (0, "更有韧性的路径是把 AI 用于减少重复劳动，把时间投入选题、关系和可验证的原创价值。"),
        ),
        ("创作者的核心竞争力将更集中于判断、关系与责任。", "平台是否应对 AI 辅助内容设置单独的分发或标识规则？"),
    ),
    (
        "企业减碳目标与短期盈利压力如何协调？",
        "讨论认为，减碳应进入经营决策而非独立报告；企业可先锁定节能降本的项目，再逐步处理需要长期投入的供应链和技术改造。",
        (
            ("夏宁", "财经主持人", "可持续商业编辑", "寻找财务与减排共同的决策语言"),
            ("方诚", "能源管理专家", "工业能效顾问", "先做可量化的节能项目"),
            ("于珂", "企业财务负责人", "资本配置顾问", "明确回报周期和风险边界"),
            ("莫晴", "供应链研究员", "采购与碳管理顾问", "减排必须覆盖关键供应商"),
            ("贺舟", "气候政策分析师", "转型风险研究员", "把政策与物理风险纳入长期成本"),
        ),
        (
            (0, "企业面对的不是减碳或盈利的单选题，而是怎样把两者放进同一套资本配置判断。"),
            (1, "设备能效和能源管理往往既减排又降本，应优先建立可审计的项目清单和基线。"),
            (2, "对回报周期较长的改造，需要清楚说明现金流影响、政策风险和不投资的潜在成本。"),
            (0, "因此可分层推进：先做节能降本项目，再为供应链和长期技术改造设定阶段性里程碑。"),
        ),
        ("减碳项目应进入统一的资本配置与风险评估体系。", "长期供应链减排成本应由采购、业务单元还是公司中心承担？"),
    ),
)


def seed_presets(session: Session) -> None:
    """Insert or complete fixed, idempotent studio demos without replacing topics."""
    now = datetime.now(UTC)
    for discussion_index, (topic, summary, cast, transcript, insight_texts) in enumerate(
        SAMPLE_DISCUSSIONS, start=1
    ):
        discussion_id = f"00000000-0000-4000-8000-{discussion_index:012d}"
        discussion = session.get(Discussion, discussion_id)
        if discussion is None:
            discussion = Discussion(id=discussion_id, topic=topic, expert_count=4, max_public_utterances=15, created_at=now, updated_at=now)
            session.add(discussion)

        discussion.status = "FINISHED"
        discussion.cast_confirmed = True
        discussion.cast_confirmed_at = now
        discussion.summary = summary
        discussion.summary_status = "succeeded"
        discussion.started_at = now
        discussion.finished_at = now
        discussion.updated_at = now

        participant_ids: list[str] = []
        for participant_index, (name, profession, title, stance) in enumerate(cast, start=1):
            participant_id = f"00000000-0000-4000-900{discussion_index}-{participant_index:012d}"
            participant_ids.append(participant_id)
            participant = session.get(Participant, participant_id)
            if participant is None:
                participant = Participant(id=participant_id, discussion_id=discussion_id, role="moderator" if participant_index == 1 else "expert", name=name, profession=profession, title=title, stance=stance, color=PALETTE[participant_index - 1], runtime_status="idle", created_at=now)
                session.add(participant)
            else:
                participant.role = "moderator" if participant_index == 1 else "expert"
                participant.name, participant.profession, participant.title, participant.stance = name, profession, title, stance
                participant.color, participant.runtime_status, participant.public_focus = PALETTE[participant_index - 1], "idle", None

        for sequence, (speaker_index, content) in enumerate(transcript, start=1):
            utterance_id = f"00000000-0000-4000-a0{discussion_index}-{sequence:012d}"
            if session.get(Utterance, utterance_id) is None:
                session.add(Utterance(id=utterance_id, discussion_id=discussion_id, participant_id=participant_ids[speaker_index], sequence=sequence, content=content, created_at=now))

        for insight_index, (kind, content) in enumerate(zip(("consensus", "disagreement"), insight_texts), start=1):
            insight_id = f"00000000-0000-4000-b0{discussion_index}-{insight_index:012d}"
            insight = session.get(Insight, insight_id)
            if insight is None:
                session.add(Insight(id=insight_id, discussion_id=discussion_id, type=kind, content=content, active=True, created_at=now, updated_at=now))
            else:
                insight.type, insight.content, insight.active, insight.updated_at = kind, content, True, now
    session.commit()
