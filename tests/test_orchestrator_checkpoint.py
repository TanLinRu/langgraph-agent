"""
Tests for orchestrator checkpoint functionality
"""
import pytest
import tempfile
import os
from pathlib import Path

from src.agent.orchestrator_checkpoint import OrchestratorCheckpoint
from src.agent.state import OrchestratorState, OrchestratorStep


class TestOrchestratorCheckpoint:
    @pytest.fixture
    def checkpoint(self, tmp_path):
        return OrchestratorCheckpoint(str(tmp_path / "memory"))

    @pytest.fixture
    def sample_state(self):
        step = OrchestratorStep(
            step_id="step-1",
            agent_id="__main_agent__",
            agent_name="Main Agent",
            description="Test step",
            depends_on=[],
            status="running",
        )
        state = OrchestratorState(
            orchestration_id="test-1",
            thread_id="thread-1",
            input_text="Test input",
            steps=[step],
            status="running",
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
        )
        return state

    def test_save_and_load(self, checkpoint, sample_state):
        saved = checkpoint.save(sample_state)
        assert saved is True

        loaded = checkpoint.load("test-1")
        assert loaded is not None
        assert loaded.orchestration_id == "test-1"
        assert loaded.thread_id == "thread-1"
        assert len(loaded.steps) == 1

    def test_load_nonexistent(self, checkpoint):
        result = checkpoint.load("nonexistent")
        assert result is None

    def test_delete(self, checkpoint, sample_state):
        checkpoint.save(sample_state)
        deleted = checkpoint.delete("test-1")
        assert deleted is True

        loaded = checkpoint.load("test-1")
        assert loaded is None

    def test_list_all(self, checkpoint, sample_state):
        checkpoint.save(sample_state)
        all_items = checkpoint.list_all()
        assert len(all_items) == 1
        assert all_items[0]["orchestration_id"] == "test-1"

    def test_save_multiple_states(self, checkpoint):
        for i in range(3):
            state = OrchestratorState(
                orchestration_id=f"test-{i}",
                thread_id="thread-1",
                input_text=f"Input {i}",
                steps=[],
                status="running",
                created_at="2024-01-01T00:00:00",
                updated_at="2024-01-01T00:00:00",
            )
            checkpoint.save(state)

        all_items = checkpoint.list_all()
        assert len(all_items) == 3