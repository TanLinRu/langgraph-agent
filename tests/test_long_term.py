import pytest
import os
import json
from pathlib import Path
from unittest.mock import patch


class TestLongTermStorage:

    def _create_manager(self, tmp_path):
        from src.agent.context.long_term import LongTermManager, LongTermConfig

        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()

        config = LongTermConfig(
            memory_dir=mem_dir,
            session_ttl_days=7,
            vector_enabled=False,
            chroma_persist_dir=str(mem_dir / "chroma"),
        )
        return LongTermManager(config)

    def test_save_session_appends_delta(self, tmp_path):
        """验证 save_session 只追加 delta 而非全量覆盖"""
        manager = self._create_manager(tmp_path)

        manager.save_session(
            thread_id="test-1",
            messages=[
                {"role": "user", "content": "第一轮"},
                {"role": "assistant", "content": "回复1"},
            ],
            metadata={"task_status": "in_progress"},
        )

        manager.save_session(
            thread_id="test-1",
            messages=[
                {"role": "user", "content": "第一轮"},
                {"role": "assistant", "content": "回复1"},
                {"role": "user", "content": "第二轮"},
                {"role": "assistant", "content": "回复2"},
            ],
            metadata={"task_status": "in_progress"},
        )

        session_file = tmp_path / "memory" / "sessions" / "test-1.jsonl"
        assert session_file.exists()

        lines = session_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        first_turn = json.loads(lines[0])
        assert len(first_turn["messages"]) == 2

        second_turn = json.loads(lines[1])
        assert second_turn["turn_offset"] == 2
        assert len(second_turn["messages"]) == 2

    def test_load_session_messages_no_duplicates(self, tmp_path):
        """验证读回的消息不重复"""
        manager = self._create_manager(tmp_path)

        manager.save_session(
            thread_id="test-2",
            messages=[
                {"role": "user", "content": "第一轮"},
                {"role": "assistant", "content": "回复1"},
            ],
            metadata={},
        )

        manager.save_session(
            thread_id="test-2",
            messages=[
                {"role": "user", "content": "第一轮"},
                {"role": "assistant", "content": "回复1"},
                {"role": "user", "content": "第二轮"},
                {"role": "assistant", "content": "回复2"},
            ],
            metadata={},
        )

        messages = manager.load_session_messages("test-2")

        assert len(messages) == 4

        contents = [m["content"] for m in messages]
        assert contents == ["第一轮", "回复1", "第二轮", "回复2"]

    def test_new_session_starts_from_zero(self, tmp_path):
        """验证新会话从 0 开始"""
        manager = self._create_manager(tmp_path)

        manager.save_session(
            thread_id="test-3",
            messages=[
                {"role": "user", "content": "唯一一轮"},
            ],
            metadata={},
        )

        messages = manager.load_session_messages("test-3")
        assert len(messages) == 1
        assert messages[0]["content"] == "唯一一轮"
