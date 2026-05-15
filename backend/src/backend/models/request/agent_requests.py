"""Agent 路由的 Pydantic 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UpdateAgentRequest(BaseModel):
    """更新 Agent 的请求体。全部字段可选。"""

    displayName: str | None = Field(default=None, description="Agent 的显示名称")
    identity: str | None = Field(default=None, description="### Identity 身份")
    style: str | None = Field(default=None, description="### Style 风格")
    defaults: str | None = Field(default=None, description="### Defaults 默认行为")
    avoid: str | None = Field(default=None, description="### Avoid 避免行为")
    coreTruths: str | None = Field(default=None, description="### Core Truths 核心真理")
    avatar: str | None = Field(default=None, description="人物形象 sprite base 名称")
    gender: str | None = Field(default=None, description="性别 male | female")
    personality: str | None = Field(default=None, description="性格描述（全部注入 system prompt）")
    catchphrases: str | None = Field(default=None, description="口头禅（每行一条，随机选一条注入）")
    memes: str | None = Field(default=None, description="梗语（每行一条，随机选一条注入）")
    model: str | None = Field(default=None, description="该 Agent 使用的模型名称（如 gpt-4o）")
    modelProvider: str | None = Field(default=None, description="模型提供商（如 openai、anthropic）")
    modelBaseUrl: str | None = Field(default=None, description="自定义 API 端点（可选）")
    backtalk_intensity: int | None = Field(default=None, description="顶嘴强度 0=沉默/1=温和/2=幽默/3=直接")


class OfficePoseIn(BaseModel):
    """办公室场景人物像素坐标与朝向（与前端 Phaser 一致）。"""

    x: float = Field(description="场景像素 X（容器原点）")
    y: float = Field(description="场景像素 Y")
    facing: str = Field(default="down", description="down | up | left | right")


class SaveOfficePosesRequest(BaseModel):
    """批量写入人物位姿；前端可 5s 节流合并提交。"""

    poses: dict[str, OfficePoseIn] = Field(default_factory=dict)


class PlanStepIn(BaseModel):
    """规划步骤（与前端 PlanStep 对齐）。"""

    id: int = Field(description="步骤序号，从 1 开始")
    title: str = Field(default="", description="步骤短标题")
    action: str = Field(default="", description="具体执行动作")
    filePath: str | None = Field(default=None, description="相关文件路径，可省略")
    confidence: str = Field(default="medium", description="high | medium | low")


class SavePlanArtifactRequest(BaseModel):
    """将解析出的 PlanArtifact 写入数据库。"""

    sessionId: str = Field(description="所属会话 id")
    name: str = Field(default="", description="任务/规划名称")
    planSummary: str = Field(default="", description="规划总览文字")
    steps: list[PlanStepIn] = Field(default_factory=list, description="步骤列表")
    rawText: str | None = Field(default=None, description="模型原始输出（可选，用于调试）")


class CreateAgentRequest(BaseModel):
    """创建 Agent 的请求体。

    用户填写完整的角色设定，系统自动写入 SOUL.md。
    SOUL.md 首行固定为 "我叫**{显示名称}**"。
    """

    profile: str = Field(
        default="default",
        description="Profile 名字，对应 ~/.hermes/ 底下的配置目录",
    )
    displayName: str = Field(
        default="",
        description="Agent 的显示名称，SOUL.md 首行用",
    )
    # 角色设定五章节
    identity: str = Field(
        default="",
        description="### Identity 身份 — 你是谁，你叫什么，核心定位",
    )
    style: str = Field(
        default="",
        description="### Style 风格 — 语言特点、语调、视觉美学",
    )
    defaults: str = Field(
        default="",
        description="### Defaults 默认行为 — 场景感知、响应协议",
    )
    avoid: str = Field(
        default="",
        description="### Avoid 避免行为 — 需要规避的内容",
    )
    coreTruths: str = Field(
        default="",
        description="### Core Truths 核心真理 — 你的世界观和终极行为准则",
    )
    avatar: str = Field(
        default="badboy",
        description="人物形象 sprite base 名称",
    )
    gender: str = Field(
        default="male",
        description="性别 male | female",
    )
    personality: str = Field(
        default="",
        description="性格描述（全部注入 system prompt）",
    )
    catchphrases: str = Field(
        default="",
        description="口头禅（每行一条）",
    )
    memes: str = Field(
        default="",
        description="梗语（每行一条）",
    )
    model: str | None = Field(
        default=None,
        description="该 Agent 使用的模型名称（如 gpt-4o），为空则使用全局默认",
    )
    modelProvider: str | None = Field(
        default=None,
        description="模型提供商（如 openai、anthropic）",
    )
    modelBaseUrl: str | None = Field(
        default=None,
        description="自定义 API 端点（可选）",
    )
    backtalk_intensity: int = Field(
        default=0,
        description="顶嘴强度 0=沉默/1=温和/2=幽默/3=直接",
    )
