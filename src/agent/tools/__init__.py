from langchain_core.tools import tool
import subprocess
import tempfile
import os
import json
import pandas as pd
from pathlib import Path
from typing import Optional

from src.agent.cli import get_available_clis, get_cli
from src.agent.cli.dispatcher import dispatch_run, start_serve, stop_serve, get_active_serves
from src.agent.schemas import ToolResult, ErrorEnvelope, ErrorType


@tool
def execute_code(code: str, timeout: int = 30) -> dict:
    """
    执行 Python 代码并返回结果。

    Use when: 你需要运行代码来验证、计算或生成结果时
    Don't use when: 只是讨论代码而不需要实际执行
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(
            ['python', temp_path],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        output = result.stdout + result.stderr
        return ToolResult(
            status="success",
            content=output or "代码执行完成，无输出",
            metadata={"exit_code": result.returncode, "timeout": timeout, "tool": "execute_code"},
        ).to_dict()
    except subprocess.TimeoutExpired:
        return ToolResult(
            status="timeout",
            content=f"执行超时 ({timeout}秒)",
            error=ErrorEnvelope(
                error_code="TOOL_EXEC_TIMEOUT",
                error_type=ErrorType.RECOVERABLE,
                message=f"执行超时 ({timeout}秒)",
                retryable=True,
                tool_name="execute_code",
            ).to_dict(),
        ).to_dict()
    except Exception as e:
        return ToolResult.from_error(e, "TOOL_EXEC_ERROR", "execute_code").to_dict()
    finally:
        try:
            os.unlink(temp_path)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"[execute_code] 临时文件清理失败: {temp_path}, {e}")


@tool
def read_file(path: str, offset: int = 0, limit: int = 100) -> dict:
    """
    读取文件内容。

    Use when: 需要查看文件内容时
    Don't use when: 文件不存在或权限不足
    """
    if _is_dangerous_path(path):
        return ToolResult(
            status="failed",
            content="错误: 禁止访问敏感路径",
            error=ErrorEnvelope(
                error_code="TOOL_PERMISSION_DENIED",
                error_type=ErrorType.FATAL,
                message="禁止访问敏感路径",
                retryable=False,
                tool_name="read_file",
            ).to_dict(),
        ).to_dict()

    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        total = len(lines)
        content = lines[offset:offset + limit]

        result = f"文件: {path}\n总行数: {total}\n"
        result += f"显示行: {offset+1}-{offset+len(content)}\n\n"
        result += "".join(f"{i+offset+1}: {line}" for i, line in enumerate(content))

        return ToolResult(
            status="success",
            content=result,
            metadata={"path": path, "lines": total, "size_bytes": os.path.getsize(path), "tool": "read_file"},
        ).to_dict()
    except FileNotFoundError:
        return ToolResult(
            status="failed",
            content=f"文件不存在: {path}",
            error=ErrorEnvelope(
                error_code="TOOL_NOT_FOUND",
                error_type=ErrorType.FATAL,
                message=f"文件不存在: {path}",
                retryable=False,
                tool_name="read_file",
            ).to_dict(),
        ).to_dict()
    except PermissionError:
        return ToolResult(
            status="failed",
            content=f"权限不足: {path}",
            error=ErrorEnvelope(
                error_code="TOOL_PERMISSION_DENIED",
                error_type=ErrorType.FATAL,
                message=f"权限不足: {path}",
                retryable=False,
                tool_name="read_file",
            ).to_dict(),
        ).to_dict()
    except Exception as e:
        return ToolResult.from_error(e, "TOOL_EXEC_ERROR", "read_file").to_dict()


@tool
def write_file(path: str, content: str, mode: str = "w") -> dict:
    """
    写入文件。

    Use when: 需要创建或更新文件时
    Don't use when: 写入系统敏感目录
    """
    if _is_dangerous_path(path):
        return ToolResult(
            status="failed",
            content="错误: 禁止写入敏感目录",
            error=ErrorEnvelope(
                error_code="TOOL_PERMISSION_DENIED",
                error_type=ErrorType.FATAL,
                message="禁止写入敏感目录",
                retryable=False,
                tool_name="write_file",
            ).to_dict(),
        ).to_dict()

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode, encoding='utf-8') as f:
            f.write(content)
        return ToolResult(
            status="success",
            content=f"已写入: {path} ({len(content)} 字符)",
            metadata={"path": path, "bytes": len(content), "tool": "write_file"},
        ).to_dict()
    except Exception as e:
        return ToolResult.from_error(e, "TOOL_EXEC_ERROR", "write_file").to_dict()


@tool
def list_directory(path: str = ".", pattern: str = "*") -> dict:
    """
    列出目录内容。

    Use when: 需要查看目录结构时
    Don't use when: 目录不存在
    """
    if _is_dangerous_path(path):
        return ToolResult(
            status="failed",
            content="错误: 禁止访问敏感路径",
            error=ErrorEnvelope(
                error_code="TOOL_PERMISSION_DENIED",
                error_type=ErrorType.FATAL,
                message="禁止访问敏感路径",
                retryable=False,
                tool_name="list_directory",
            ).to_dict(),
        ).to_dict()

    try:
        from glob import glob
        files = glob(os.path.join(path, pattern))

        if not files:
            return ToolResult(
                status="success",
                content=f"目录为空: {path}",
                metadata={"path": path, "count": 0, "tool": "list_directory"},
            ).to_dict()

        result = f"目录: {path}\n"
        for f in files:
            size = os.path.getsize(f)
            is_dir = "DIR" if os.path.isdir(f) else "FILE"
            result += f"{is_dir:6} {size:>10} {f}\n"

        return ToolResult(
            status="success",
            content=result,
            metadata={"path": path, "count": len(files), "tool": "list_directory"},
        ).to_dict()
    except FileNotFoundError:
        return ToolResult(
            status="failed",
            content=f"目录不存在: {path}",
            error=ErrorEnvelope(
                error_code="TOOL_NOT_FOUND",
                error_type=ErrorType.FATAL,
                message=f"目录不存在: {path}",
                retryable=False,
                tool_name="list_directory",
            ).to_dict(),
        ).to_dict()
    except Exception as e:
        return ToolResult.from_error(e, "TOOL_EXEC_ERROR", "list_directory").to_dict()


@tool
def data_processor(
    operation: str,
    file_path: str,
    params: Optional[dict] = None
) -> dict:
    """
    处理结构化数据（CSV/JSON）。

    Use when: 需要清洗、转换、聚合数据时
    Don't use when: 只是读取文件查看内容
    """
    params = params or {}

    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith('.json'):
            df = pd.read_json(file_path)
        else:
            return ToolResult(
                status="failed",
                content=f"不支持的文件格式: {file_path}",
                error=ErrorEnvelope(
                    error_code="TOOL_ARGUMENT_ERROR",
                    error_type=ErrorType.FATAL,
                    message=f"不支持的文件格式: {file_path}",
                    retryable=False,
                    tool_name="data_processor",
                ).to_dict(),
            ).to_dict()

        if operation == "head":
            n = params.get("n", 5)
            content = f"前 {n} 行:\n{df.head(n).to_string()}"
        elif operation == "describe":
            content = f"数据统计:\n{df.describe().to_string()}"
        elif operation == "info":
            content = f"数据信息:\n列: {list(df.columns)}\n形状: {df.shape}\n类型:\n{df.dtypes}"
        elif operation == "dropna":
            before = len(df)
            df_clean = df.dropna()
            content = f"已删除 {before - len(df_clean)} 行缺失数据，剩余 {len(df_clean)} 行"
        elif operation == "groupby":
            col = params.get("group_col")
            agg_col = params.get("agg_col")
            if not col or not agg_col:
                return ToolResult(
                    status="failed",
                    content="错误: 需要指定 group_col 和 agg_col",
                    error=ErrorEnvelope(
                        error_code="TOOL_ARGUMENT_ERROR",
                        error_type=ErrorType.FATAL,
                        message="需要指定 group_col 和 agg_col",
                        retryable=False,
                        tool_name="data_processor",
                    ).to_dict(),
                ).to_dict()
            result_df = df.groupby(col)[agg_col].agg(['sum', 'mean', 'count'])
            content = f"分组统计:\n{result_df.to_string()}"
        elif operation == "filter":
            col = params.get("column")
            val = params.get("value")
            if not col:
                return ToolResult(
                    status="failed",
                    content="错误: 需要指定 column",
                    error=ErrorEnvelope(
                        error_code="TOOL_ARGUMENT_ERROR",
                        error_type=ErrorType.FATAL,
                        message="需要指定 column",
                        retryable=False,
                        tool_name="data_processor",
                    ).to_dict(),
                ).to_dict()
            filtered = df[df[col] == val]
            content = f"筛选出 {len(filtered)} 行\n{filtered.head(10).to_string()}"
        else:
            return ToolResult(
                status="failed",
                content=f"未知操作: {operation}",
                error=ErrorEnvelope(
                    error_code="TOOL_ARGUMENT_ERROR",
                    error_type=ErrorType.FATAL,
                    message=f"未知操作: {operation}",
                    retryable=False,
                    tool_name="data_processor",
                ).to_dict(),
            ).to_dict()

        return ToolResult(
            status="success",
            content=content,
            metadata={"file_path": file_path, "operation": operation, "rows": len(df), "cols": len(df.columns), "tool": "data_processor"},
        ).to_dict()

    except FileNotFoundError:
        return ToolResult(
            status="failed",
            content=f"文件不存在: {file_path}",
            error=ErrorEnvelope(
                error_code="TOOL_NOT_FOUND",
                error_type=ErrorType.FATAL,
                message=f"文件不存在: {file_path}",
                retryable=False,
                tool_name="data_processor",
            ).to_dict(),
        ).to_dict()
    except Exception as e:
        return ToolResult.from_error(e, "TOOL_EXEC_ERROR", "data_processor").to_dict()


@tool
def search_files(path: str, pattern: str, file_type: str = "*") -> dict:
    """
    搜索文件内容。

    Use when: 需要在代码库中搜索关键词时
    Don't use when: 搜索大文件或二进制文件
    """
    try:
        import re
        results = []
        errors = []

        for root, dirs, files in os.walk(path):
            for f in files:
                if not _match_pattern(f, file_type):
                    continue

                file_path = os.path.join(root, f)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as fp:
                        for i, line in enumerate(fp, 1):
                            if re.search(pattern, line):
                                results.append(f"{file_path}:{i}: {line.strip()}")
                except Exception as e:
                    errors.append(f"读取失败 {file_path}: {e}")

        if not results:
            if errors:
                return ToolResult(
                    status="partial",
                    content=f"搜索完成，但有 {len(errors)} 个文件读取失败:\n" + "\n".join(errors[:10]),
                    metadata={"errors": errors, "tool": "search_files"},
                ).to_dict()
            return ToolResult(
                status="success",
                content=f"未找到匹配: {pattern}",
                metadata={"tool": "search_files"},
            ).to_dict()

        err_note = ""
        status = "success"
        metadata = {"matched_count": len(results), "errors": errors, "tool": "search_files"}
        if errors:
            err_note = f"\n\n[注：{len(errors)} 个文件读取失败]"
            status = "partial"

        return ToolResult(
            status=status,
            content=f"找到 {len(results)} 处匹配:\n" + "\n".join(results[:50]) + err_note,
            metadata=metadata,
        ).to_dict()

    except Exception as e:
        return ToolResult.from_error(e, "TOOL_EXEC_ERROR", "search_files").to_dict()


def _is_dangerous_path(path: str) -> bool:
    """检查危险路径"""
    dangerous = ['/etc', '/root', '/sys', '/proc', 'C:\\Windows']
    normalized = os.path.normpath(path)
    if any(normalized.startswith(d) for d in dangerous):
        return True
    if '..' in path:
        return True
    if os.path.isabs(path) and not path.startswith(os.getcwd()):
        return True
    return False


def _match_pattern(filename: str, pattern: str) -> bool:
    """匹配文件模式"""
    if pattern == "*":
        return True
    if "*" in pattern:
        import fnmatch
        return fnmatch.fnmatch(filename, pattern)
    return filename.endswith(pattern)


@tool
def dispatch_to_cli(
    task: str,
    cli_name: str = "opencode",
    working_dir: str = ".",
    mode: str = "run",
    auto_approve: bool = True,
    timeout: int = 600,
) -> dict:
    """
    调度编码任务到外部 Coding CLI (opencode/claude)。

    Use when: 需要执行复杂的编码任务，如重构、新功能开发、多文件修改
    Don't use when: 简单的文件读写、运行单个脚本、数据查询

    Args:
        task: 任务描述，详细说明需要做什么
        cli_name: 使用的 CLI 名称 (opencode 或 claude)
        working_dir: 项目工作目录
        mode: 执行模式 (run=同步, serve=持久服务)
        auto_approve: 是否自动批准权限
        timeout: 超时时间（秒）
    """
    cli = get_cli(cli_name)
    if not cli:
        return ToolResult(
            status="failed",
            content=f"错误: 未找到 CLI '{cli_name}'",
        ).to_dict()
    if not cli.get("available"):
        return ToolResult(
            status="failed",
            content=f"错误: CLI '{cli_name}' 未安装",
        ).to_dict()
    if mode not in cli.get("modes", []):
        return ToolResult(
            status="failed",
            content=f"错误: CLI '{cli_name}' 不支持 {mode} 模式",
        ).to_dict()

    if mode == "serve":
        result = start_serve(
            cli_name=cli_name,
            cli_path=cli["path"],
            working_dir=working_dir,
        )
    else:
        result = dispatch_run(
            cli_name=cli_name,
            cli_path=cli["path"],
            task=task,
            working_dir=working_dir,
            auto_approve=auto_approve,
            timeout=timeout,
        )

    return ToolResult(
        status="success",
        content=json.dumps(result, ensure_ascii=False, indent=2),
        metadata={"cli_name": cli_name, "mode": mode, "tool": "dispatch_to_cli"},
    ).to_dict()


@tool
def list_clis() -> dict:
    """
    列出所有可用的 Coding CLI 及其状态。

    Use when: 需要了解有哪些编码工具可用时
    """
    clis = get_available_clis()
    if not clis:
        return ToolResult(
            status="success",
            content="没有可用的 Coding CLI",
        ).to_dict()

    lines = ["可用的 Coding CLI:"]
    for cli in clis:
        modes = ", ".join(cli.get("modes", []))
        caps = ", ".join(cli.get("capabilities", []))
        lines.append(f"- {cli['name']} (路径: {cli['path']})")
        lines.append(f"  模式: {modes}")
        lines.append(f"  能力: {caps}")

    return ToolResult(
        status="success",
        content="\n".join(lines),
        metadata={"count": len(clis), "tool": "list_clis"},
    ).to_dict()


@tool
def list_serves() -> dict:
    """
    列出所有活跃的 CLI 服务。

    Use when: 需要查看正在运行的 serve 服务时
    """
    serves = get_active_serves()
    if not serves:
        return ToolResult(
            status="success",
            content="没有活跃的服务",
        ).to_dict()

    lines = ["活跃的 CLI 服务:"]
    for s in serves:
        status = "运行中" if s["running"] else "已停止"
        lines.append(f"- {s['serve_id']} ({s['cli_name']}) - {status}")
        lines.append(f"  PID: {s['pid']}, 目录: {s['working_dir']}")
        lines.append(f"  启动时间: {s['started_at']}")

    return ToolResult(
        status="success",
        content="\n".join(lines),
        metadata={"count": len(serves), "tool": "list_serves"},
    ).to_dict()


@tool
def stop_serve_tool(serve_id: str) -> dict:
    """
    停止指定的 CLI 服务。

    Use when: 需要停止不再需要的 serve 服务时
    """
    result = stop_serve(serve_id)
    return ToolResult(
        status="success",
        content=json.dumps(result, ensure_ascii=False, indent=2),
        metadata={"serve_id": serve_id, "tool": "stop_serve_tool"},
    ).to_dict()


@tool
def dispatch_via_acp(
    task: str,
    skill: Optional[str] = None,
    timeout: int = 300,
) -> dict:
    """
    通过 ACP 协议调度外部 opencode 执行编码任务。

    Use when: 需要执行复杂的编码任务，通过 ACP 协议调用 opencode 时
    Don't use when: 简单的文件操作或已有专用工具

    Args:
        task: 任务描述，详细说明需要做什么
        skill: 可选的 skill 名称
        timeout: 超时时间（秒）
    """
    from src.agent.acp_client import get_acp_client

    try:
        client = get_acp_client(timeout=timeout)

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                client.call(
                    prompt=task,
                    system_prompt="你是一个代码开发助手，负责执行用户请求的编码任务。",
                    skill=skill,
                )
            )
        finally:
            loop.close()

        return ToolResult(
            status="success",
            content=result,
            metadata={"skill": skill, "timeout": timeout, "tool": "dispatch_via_acp"},
        ).to_dict()

    except Exception as e:
        return ToolResult.from_error(e, "TOOL_EXEC_ERROR", "dispatch_via_acp").to_dict()


# L3 Tool Result manager (set by Agent during init)
_tool_result_manager = None


def set_tool_result_manager(mgr) -> None:
    """配置 tool result 持久化管理器，供 read_tool_detail 使用"""
    global _tool_result_manager
    _tool_result_manager = mgr


@tool
def read_tool_detail(thread_id: str, tool_call_id: str) -> str:
    """
    读取完整的历史工具执行结果。

    Use when: 你需要查看之前某次工具调用的完整输出（当前热区中只有前 200 字摘要）
    Don't use when: 当前对话中刚刚执行完的工具，结果已经在回复中
    """
    from src.agent.context import LongTermManager, LongTermConfig
    mgr = _tool_result_manager
    if mgr is None:
        mgr = LongTermManager(LongTermConfig())
    result = mgr.load_tool_result(thread_id, tool_call_id)
    if result:
        import textwrap
        content = result["content"]
        if len(content) > 8000:
            content = content[:8000] + "\n\n... (结果过长，仅显示前 8000 字符)"
        return (
            f"## Tool: {result['tool_name']}\n"
            f"Status: {result['status']}\n"
            f"Called at: {result.get('created_at', 'N/A')}\n\n"
            f"{content}"
        )
    return f"未找到工具执行记录: tool_call_id={tool_call_id}"


TOOLS = [
    execute_code,
    read_file,
    write_file,
    list_directory,
    data_processor,
    search_files,
    dispatch_to_cli,
    dispatch_via_acp,
    list_clis,
    list_serves,
    stop_serve_tool,
    read_tool_detail,
]

__all__ = ["TOOLS", "read_tool_detail", "set_tool_result_manager"]