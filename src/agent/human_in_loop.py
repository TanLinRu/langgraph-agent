"""
Human-in-Loop (HITL) - Approval System

提供:
- 审批请求创建
- 等待审批
- 审批结果处理
- 审批历史记录
"""
import asyncio
import logging
import time
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalType(Enum):
    TOOL_EXECUTION = "tool_execution"
    WRITE_OPERATION = "write_operation"
    WORKFLOW_STEP = "workflow_step"
    CODE_EXECUTION = "code_execution"
    RESOURCE_ACCESS = "resource_access"


@dataclass
class ApprovalRequest:
    request_id: str
    approval_type: ApprovalType
    description: str
    details: dict = field(default_factory=dict)
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0
    approved_by: Optional[str] = None
    rejected_by: Optional[str] = None
    comment: Optional[str] = None


class HumanInTheLoop:
    """人机交互控制器"""

    def __init__(self, default_timeout: float = 300.0):
        self.default_timeout = default_timeout
        self._pending_approvals: dict[str, ApprovalRequest] = {}
        self._approval_events: dict[str, asyncio.Event] = {}
        self._approval_callbacks: list[Callable] = []

        self._critical_types = {
            ApprovalType.WRITE_OPERATION,
            ApprovalType.CODE_EXECUTION,
            ApprovalType.RESOURCE_ACCESS,
        }

    def register_callback(self, callback: Callable):
        """注册审批回调"""
        self._approval_callbacks.append(callback)

    def is_critical_operation(self, approval_type: ApprovalType) -> bool:
        """判断是否需要审批"""
        return approval_type in self._critical_types

    async def request_approval(
        self,
        request_id: str,
        approval_type: ApprovalType,
        description: str,
        details: dict = None,
        timeout: float = None,
    ) -> bool:
        """请求审批"""
        if not self.is_critical_operation(approval_type):
            return True

        timeout = timeout or self.default_timeout

        request = ApprovalRequest(
            request_id=request_id,
            approval_type=approval_type,
            description=description,
            details=details or {},
            expires_at=time.time() + timeout,
        )

        self._pending_approvals[request_id] = request
        self._approval_events[request_id] = asyncio.Event()

        for callback in self._approval_callbacks:
            try:
                await callback(request)
            except Exception as e:
                logger.error(f"[HITL] Callback error: {e}")

        logger.info(f"[HITL] Approval requested: {request_id} ({approval_type.value})")

        try:
            approved = await asyncio.wait_for(
                self._approval_events[request_id].wait(),
                timeout=timeout
            )
            return approved
        except asyncio.TimeoutError:
            request.status = ApprovalStatus.EXPIRED
            logger.warning(f"[HITL] Approval expired: {request_id}")
            return False

    async def approve(
        self,
        request_id: str,
        approved_by: str = "user",
        comment: str = None,
    ) -> bool:
        """批准请求"""
        request = self._pending_approvals.get(request_id)
        if not request:
            logger.warning(f"[HITL] Approval request not found: {request_id}")
            return False

        request.status = ApprovalStatus.APPROVED
        request.approved_by = approved_by
        request.comment = comment

        if request_id in self._approval_events:
            self._approval_events[request_id].set()

        logger.info(f"[HITL] Approved: {request_id} by {approved_by}")
        return True

    async def reject(
        self,
        request_id: str,
        rejected_by: str = "user",
        comment: str = None,
    ) -> bool:
        """拒绝请求"""
        request = self._pending_approvals.get(request_id)
        if not request:
            logger.warning(f"[HITL] Approval request not found: {request_id}")
            return False

        request.status = ApprovalStatus.REJECTED
        request.rejected_by = rejected_by
        request.comment = comment

        if request_id in self._approval_events:
            self._approval_events[request_id].set()

        logger.info(f"[HITL] Rejected: {request_id} by {rejected_by}")
        return True

    def get_pending(self) -> list[ApprovalRequest]:
        """获取待审批列表"""
        return [
            r for r in self._pending_approvals.values()
            if r.status == ApprovalStatus.PENDING
        ]

    def get_history(self, limit: int = 50) -> list[dict]:
        """获取审批历史"""
        sorted_requests = sorted(
            self._pending_approvals.values(),
            key=lambda r: r.created_at,
            reverse=True
        )
        return [
            {
                "request_id": r.request_id,
                "type": r.approval_type.value,
                "description": r.description,
                "status": r.status.value,
                "created_at": r.created_at,
                "decided_by": r.approved_by or r.rejected_by,
            }
            for r in sorted_requests[:limit]
        ]

    def clear_expired(self):
        """清理过期请求"""
        now = time.time()
        expired = [
            rid for rid, r in self._pending_approvals.items()
            if r.status == ApprovalStatus.PENDING and r.expires_at < now
        ]
        for rid in expired:
            self._pending_approvals[rid].status = ApprovalStatus.EXPIRED
            if rid in self._approval_events:
                self._approval_events[rid].set()


_hitl: Optional[HumanInTheLoop] = None


def get_hitl() -> HumanInTheLoop:
    global _hitl
    if _hitl is None:
        _hitl = HumanInTheLoop()
    return _hitl