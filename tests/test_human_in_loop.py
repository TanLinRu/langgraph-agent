"""
Tests for Human-in-the-Loop
"""
import pytest
import asyncio
from src.agent.human_in_loop import (
    HumanInTheLoop, ApprovalRequest, ApprovalType, ApprovalStatus
)


class TestHumanInTheLoop:
    def test_auto_approve_non_critical(self):
        hitl = HumanInTheLoop()
        result = hitl.is_critical_operation(ApprovalType.WORKFLOW_STEP)
        assert result is False

    def test_get_pending(self):
        hitl = HumanInTheLoop()
        hitl._pending_approvals = {
            "req-1": ApprovalRequest("req-1", ApprovalType.WRITE_OPERATION, "test"),
            "req-2": ApprovalRequest("req-2", ApprovalType.WRITE_OPERATION, "test2", status=ApprovalStatus.APPROVED),
        }

        pending = hitl.get_pending()
        assert len(pending) == 1
        assert pending[0].request_id == "req-1"

    def test_is_critical_operation(self):
        hitl = HumanInTheLoop()
        assert hitl.is_critical_operation(ApprovalType.WRITE_OPERATION) is True
        assert hitl.is_critical_operation(ApprovalType.WORKFLOW_STEP) is False

    def test_get_pending(self):
        hitl = HumanInTheLoop()
        hitl._pending_approvals = {
            "req-1": ApprovalRequest("req-1", ApprovalType.WRITE_OPERATION, "test"),
            "req-2": ApprovalRequest("req-2", ApprovalType.WRITE_OPERATION, "test2", status=ApprovalStatus.APPROVED),
        }

        pending = hitl.get_pending()
        assert len(pending) == 1
        assert pending[0].request_id == "req-1"