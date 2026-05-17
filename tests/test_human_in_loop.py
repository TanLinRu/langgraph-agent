import pytest
from unittest.mock import patch, MagicMock
from src.agent.human_in_loop import (
    HumanInTheLoop,
    ApprovalType,
    ApprovalStatus,
)


class TestHumanInTheLoopBugFix:
    @pytest.fixture
    def hitl(self):
        hitl = HumanInTheLoop()
        hitl._pending_approvals.clear()
        hitl._approval_events.clear()
        return hitl

    def test_approval_returns_true_on_approve(self, hitl):
        request_id = "test-approve-1"

        async def approve_later():
            await hitl.approve(request_id, "tester")

        async def request():
            return await hitl.request_approval(
                request_id=request_id,
                approval_type=ApprovalType.CODE_EXECUTION,
                description="test approve",
                timeout=2.0,
            )

        import asyncio

        async def run():
            task = asyncio.create_task(request())
            await asyncio.sleep(0.05)
            await approve_later()
            return await task

        result = asyncio.run(run())
        assert result is True

    def test_approval_returns_false_on_reject(self, hitl):
        request_id = "test-reject-1"

        async def reject_later():
            await hitl.reject(request_id, "tester")

        async def request():
            return await hitl.request_approval(
                request_id=request_id,
                approval_type=ApprovalType.CODE_EXECUTION,
                description="test reject",
                timeout=2.0,
            )

        import asyncio

        async def run():
            task = asyncio.create_task(request())
            await asyncio.sleep(0.05)
            await reject_later()
            return await task

        result = asyncio.run(run())
        assert result is False

    def test_auto_approve_non_critical(self, hitl):
        request_id = "test-non-critical"

        import asyncio

        async def run():
            return await hitl.request_approval(
                request_id=request_id,
                approval_type=ApprovalType.WORKFLOW_STEP,
                description="workflow step",
                timeout=1.0,
            )

        result = asyncio.run(run())
        assert result is True

    def test_approval_status_reflects_actual_decision(self, hitl):
        request_id = "test-status-check"

        import asyncio

        async def approve_later():
            await asyncio.sleep(0.05)
            await hitl.approve(request_id, "user1")

        async def request():
            return await hitl.request_approval(
                request_id=request_id,
                approval_type=ApprovalType.CODE_EXECUTION,
                description="status check",
                timeout=2.0,
            )

        async def run():
            task = asyncio.create_task(request())
            await approve_later()
            return await task

        result = asyncio.run(run())
        assert result is True

    def test_concurrent_approval_requests(self, hitl):
        request_id_1 = "test-concurrent-1"
        request_id_2 = "test-concurrent-2"

        import asyncio

        async def approve_request_1():
            await asyncio.sleep(0.05)
            await hitl.approve(request_id_1, "tester")

        async def reject_request_2():
            await asyncio.sleep(0.05)
            await hitl.reject(request_id_2, "tester")

        async def run():
            r1 = await hitl.request_approval(
                request_id=request_id_1,
                approval_type=ApprovalType.CODE_EXECUTION,
                description="concurrent 1",
                timeout=2.0,
            )
            r2 = await hitl.request_approval(
                request_id=request_id_2,
                approval_type=ApprovalType.CODE_EXECUTION,
                description="concurrent 2",
                timeout=2.0,
            )
            return (r1, r2)

        async def run_all():
            r1_task = asyncio.create_task(hitl.request_approval(
                request_id=request_id_1,
                approval_type=ApprovalType.CODE_EXECUTION,
                description="concurrent 1",
                timeout=2.0,
            ))
            r2_task = asyncio.create_task(hitl.request_approval(
                request_id=request_id_2,
                approval_type=ApprovalType.CODE_EXECUTION,
                description="concurrent 2",
                timeout=2.0,
            ))
            await asyncio.sleep(0.05)
            await hitl.approve(request_id_1, "tester")
            await hitl.reject(request_id_2, "tester")
            r1, r2 = await asyncio.gather(r1_task, r2_task)
            return (r1, r2)

        r1, r2 = asyncio.run(run_all())
        assert r1 is True
        assert r2 is False