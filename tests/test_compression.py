"""Tests for context compression functionality"""
import os
from unittest.mock import patch, MagicMock

import pytest

from src.agent.context.compression import (
    ContextCompressor,
    CompressionConfig,
    CompressedTurn,
    CompressionResult,
)


def should_use_real_api():
    return os.getenv("USE_REAL_API", "false").lower() == "true"


@pytest.mark.unit
@pytest.mark.context
class TestContextCompression:
    """Test suite for context compression"""

    @pytest.fixture
    def config(self):
        return CompressionConfig(
            max_tokens=1000,
            trigger_threshold=0.1,
            keep_recent=2,
            summary_max_tokens=100,
            hot_zone_size=3,
        )

    @pytest.fixture
    def compressor(self, config):
        return ContextCompressor(config)


@pytest.mark.unit
@pytest.mark.context
class TestCompressionResult:
    def test_result_has_errors_field(self):
        result = CompressionResult(
            compressed_messages=[],
            compressed_turns=[],
            original_count=10,
            compressed_count=5,
            compression_ratio=0.5,
            token_saved=100,
            errors=[],
            warnings=[],
        )
        assert hasattr(result, "errors")
        assert result.errors == []

    def test_result_has_warnings_field(self):
        result = CompressionResult(
            compressed_messages=[],
            compressed_turns=[],
            original_count=10,
            compressed_count=5,
            compression_ratio=0.5,
            token_saved=100,
            errors=[],
            warnings=["test warning"],
        )
        assert hasattr(result, "warnings")
        assert len(result.warnings) == 1

    def test_has_errors_false_when_empty(self):
        result = CompressionResult(
            compressed_messages=[],
            compressed_turns=[],
            original_count=0,
            compressed_count=0,
            compression_ratio=1.0,
            token_saved=0,
        )
        assert result.has_errors() is False

    def test_has_warnings_false_when_empty(self):
        result = CompressionResult(
            compressed_messages=[],
            compressed_turns=[],
            original_count=0,
            compressed_count=0,
            compression_ratio=1.0,
            token_saved=0,
        )
        assert result.has_warnings() is False

    def test_compression_ratio_calculation(self):
        result = CompressionResult(
            compressed_messages=["a", "b"],
            compressed_turns=[],
            original_count=10,
            compressed_count=2,
            compression_ratio=0.2,
            token_saved=80,
        )
        assert result.compression_ratio == 0.2


@pytest.mark.unit
@pytest.mark.context
class TestCompressReturnsCompressionResult:
    @pytest.fixture
    def config(self):
        return CompressionConfig(
            max_tokens=1000,
            trigger_threshold=0.1,
            keep_recent=2,
            summary_max_tokens=100,
            hot_zone_size=3,
        )

    def test_compress_returns_compression_result(self, config):
        compressor = ContextCompressor(config)
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = compressor.compress(messages)
        assert isinstance(result, CompressionResult)
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")
        assert result.compressed_messages is not None


@pytest.mark.unit
@pytest.mark.context
class TestCompressedTurn:
    def test_compressed_turn_creation(self):
        turn = CompressedTurn(
            turn_index=0,
            user_intent="test intent",
            key_facts=["fact1"],
            tool_actions=[{"name": "test_tool"}],
            unresolved=["unresolved1"],
            compression_rationale="test",
        )
        assert turn.turn_index == 0
        assert turn.user_intent == "test intent"
        assert len(turn.key_facts) == 1
        assert len(turn.unresolved) == 1


@pytest.mark.integration
@pytest.mark.context
class TestEnrichLLM:
    @pytest.fixture
    def config(self):
        return CompressionConfig(
            max_tokens=1000,
            trigger_threshold=0.1,
            keep_recent=2,
            summary_max_tokens=100,
            hot_zone_size=3,
        )

    def test_enrich_with_llm_no_op_when_no_llm(self, config):
        compressor = ContextCompressor(config)
        compressor.llm = None
        turns = [
            CompressedTurn(
                turn_index=0,
                user_intent="test",
                key_facts=[],
                tool_actions=[],
                unresolved=[],
            )
        ]
        compressor._enrich_turns_with_llm(turns)
        assert turns[0].key_facts == []