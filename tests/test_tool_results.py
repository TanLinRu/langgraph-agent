import pytest
import json
from unittest.mock import patch
from src.agent.schemas import ToolResult, ErrorEnvelope, ErrorType


@pytest.mark.unit
@pytest.mark.tools
class TestToolResult:
    """ToolResult 数据结构测试 - 单元测试"""

    def test_creation_success(self):
        tr = ToolResult(status="success", content="hello")
        assert tr.status == "success"
        assert tr.content == "hello"
        assert tr.error is None

    def test_creation_failed(self):
        tr = ToolResult(status="failed", content="error occurred")
        assert tr.status == "failed"
        assert tr.content == "error occurred"

    def test_creation_with_metadata(self):
        tr = ToolResult(
            status="success",
            content="result",
            metadata={"rows": 10, "cols": 5},
            idempotency_key="test-key-123",
        )
        assert tr.metadata["rows"] == 10
        assert tr.idempotency_key == "test-key-123"

    def test_to_dict(self):
        tr = ToolResult(
            status="success",
            content="test",
            metadata={"key": "value"},
            idempotency_key="key-1",
        )
        d = tr.to_dict()
        assert d["status"] == "success"
        assert d["content"] == "test"
        assert d["metadata"] == {"key": "value"}
        assert d["idempotency_key"] == "key-1"
        assert "error" in d

    def test_from_error(self):
        exc = ValueError("invalid input")
        tr = ToolResult.from_error(exc, "TOOL_ARGUMENT_ERROR", "test_tool")
        assert tr.status == "failed"
        assert "invalid input" in tr.content
        assert tr.error is not None
        assert tr.error["error_code"] == "TOOL_ARGUMENT_ERROR"

    def test_from_error_default_code(self):
        exc = RuntimeError("runtime error")
        tr = ToolResult.from_error(exc)
        assert tr.status == "failed"
        assert tr.error["error_code"] == "TOOL_EXEC_ERROR"

    def test_serialization_roundtrip(self):
        original = ToolResult(
            status="partial",
            content="some content",
            metadata={"count": 5},
            idempotency_key="round-trip-test",
        )
        d = original.to_dict()
        restored = ToolResult(**{k: v for k, v in d.items() if k in ["status", "content", "error", "metadata", "idempotency_key"]})
        assert restored.status == original.status
        assert restored.content == original.content
        assert restored.metadata == original.metadata


@pytest.mark.unit
@pytest.mark.tools
class TestToolResultErrorEnvelope:
    """ErrorEnvelope 在 ToolResult 中的测试"""

    def test_error_envelope_in_to_dict(self):
        tr = ToolResult(
            status="failed",
            content="tool failed",
            error=ErrorEnvelope(
                error_code="TOOL_EXEC_ERROR",
                error_type=ErrorType.RECOVERABLE,
                message="tool failed",
            ).to_dict(),
        )
        d = tr.to_dict()
        assert d["error"]["error_code"] == "TOOL_EXEC_ERROR"

    def test_timeout_status(self):
        tr = ToolResult(
            status="timeout",
            content="operation timed out",
            error=ErrorEnvelope(
                error_code="TOOL_EXEC_TIMEOUT",
                error_type=ErrorType.RECOVERABLE,
                message="timeout",
                retryable=True,
            ).to_dict(),
        )
        assert tr.status == "timeout"
        d = tr.to_dict()
        assert d["status"] == "timeout"


@pytest.mark.integration
@pytest.mark.tools
class TestToolsReturnToolResult:
    """工具返回格式测试 - 集成测试"""

    def test_execute_code_returns_dict(self):
        from src.agent.tools import execute_code

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result = __import__("types").SimpleNamespace(
                stdout="ok", stderr="", returncode=0
            )
            result = execute_code.invoke({"code": "print(1)", "timeout": 5})
            assert isinstance(result, dict)
            assert result["status"] == "success"
            assert result["content"] == "ok"

    def test_read_file_returns_dict(self):
        from src.agent.tools import read_file

        with patch("builtins.open", side_effect=FileNotFoundError("no such file")):
            result = read_file.invoke({"path": "/nonexistent/file.txt"})
            assert isinstance(result, dict)
            assert result["status"] == "failed"
            assert "error" in result

    def test_write_file_returns_dict(self, tmp_path):
        from src.agent.tools import write_file

        test_file = str(tmp_path / "test.txt")
        with patch("src.agent.tools._is_dangerous_path", return_value=False):
            result = write_file.invoke({"path": test_file, "content": "hello"})
            assert isinstance(result, dict)
            assert result["status"] == "success"
            assert "已写入" in result["content"]

    def test_list_directory_returns_dict(self):
        from src.agent.tools import list_directory

        with patch("glob.glob", return_value=[]):
            result = list_directory.invoke({"path": "/tmp"})
            assert isinstance(result, dict)
            assert result["status"] == "success"

    def test_search_files_returns_dict(self):
        from src.agent.tools import search_files

        with patch("os.walk", return_value=[]):
            result = search_files.invoke({"path": "/tmp", "pattern": "test"})
            assert isinstance(result, dict)
            assert "status" in result

    def test_stop_serve_tool_returns_dict(self):
        from src.agent.tools import stop_serve_tool

        with patch("src.agent.tools.stop_serve", return_value={"stopped": True}):
            result = stop_serve_tool.invoke({"serve_id": "test-id"})
            assert isinstance(result, dict)
            assert result["status"] == "success"

    def test_list_clis_returns_dict(self):
        from src.agent.tools import list_clis

        with patch("src.agent.tools.get_available_clis", return_value=[]):
            result = list_clis.invoke({})
            assert isinstance(result, dict)
            assert result["status"] == "success"

    def test_list_serves_returns_dict(self):
        from src.agent.tools import list_serves

        with patch("src.agent.tools.get_active_serves", return_value=[]):
            result = list_serves.invoke({})
            assert isinstance(result, dict)
            assert result["status"] == "success"