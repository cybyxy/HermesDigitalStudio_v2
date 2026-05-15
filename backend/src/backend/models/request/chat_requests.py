"""Chat 路由的 Pydantic 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    """创建会话的请求体。"""
    agentId: str | None = None  # 指定 Agent ID，不指定则使用第一个 Agent
    cols: int = 120             # 终端宽度（字符数）
    parentSessionId: str | None = None  # 若指定，表示该 session 是从另一个 session 压缩/续接而来的


class SubmitPromptRequest(BaseModel):
    """提交用户输入的请求体。"""
    sessionId: str = ""  # 目标会话 ID
    text: str = ""       # 用户输入的文本
    attachments: list[str] = []  # 附件文件路径列表


class OrchestratedChatRequest(BaseModel):
    """Bungalow 风格编排：主轮 + 解析 assistant ``@`` 同伴（用户 handoff 仍走 ``submit_prompt`` 分支）。"""
    sessionId: str = ""
    text: str = ""
    attachments: list[str] = []
    autoPeer: bool = True
    completeTimeout: float = 480.0
    cols: int = 120


class DelegationReadyRequest(BaseModel):
    """Studio 场景：同伴 relay 前走位完成后的回执（对应 ``orch_delegation_start.delegation_token``）。"""

    delegationToken: str = ""


class ApprovalRequest(BaseModel):
    """响应工具调用审批的请求体。"""
    session_id: str = ""
    choice: str = ""     # 审批选项: "once"（本次）| "session"（本次会话）| "deny"（拒绝）
    all: bool = False


class ClarifyRequest(BaseModel):
    """响应多选项澄清请求的请求体。"""
    session_id: str = ""
    request_id: str = ""  # 澄清请求的唯一 ID
    answer: str = ""      # 用户选择的答案


class PlanChainStepIn(BaseModel):
    """规划链单步（与前端 PlanStep 对齐）。"""

    id: int = 0
    title: str = ""
    action: str = ""
    filePath: str | None = None


class PlanChainStartRequest(BaseModel):
    """启动服务端顺序执行规划链。"""

    sessionId: str = ""
    planAnchorTs: int = 0
    name: str = ""
    planSummary: str = ""
    steps: list[PlanChainStepIn] = []
    stepTimeout: float = 900.0
    rawText: str | None = None
