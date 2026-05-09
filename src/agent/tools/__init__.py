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


@tool
def execute_code(code: str, timeout: int = 30) -> str:
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
        return output or "代码执行完成，无输出"
    except subprocess.TimeoutExpired:
        return f"执行超时 ({timeout}秒)"
    except Exception as e:
        return f"执行错误: {str(e)}"
    finally:
        try:
            os.unlink(temp_path)
        except:
            pass


@tool
def read_file(path: str, offset: int = 0, limit: int = 100) -> str:
    """
    读取文件内容。

    Use when: 需要查看文件内容时
    Don't use when: 文件不存在或权限不足
    """
    if _is_dangerous_path(path):
        return "错误: 禁止访问敏感路径"

    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total = len(lines)
        content = lines[offset:offset + limit]
        
        result = f"文件: {path}\n总行数: {total}\n"
        result += f"显示行: {offset+1}-{offset+len(content)}\n\n"
        result += "".join(f"{i+offset+1}: {line}" for i, line in enumerate(content))
        
        return result
    except FileNotFoundError:
        return f"文件不存在: {path}"
    except PermissionError:
        return f"权限不足: {path}"
    except Exception as e:
        return f"读取错误: {str(e)}"


@tool
def write_file(path: str, content: str, mode: str = "w") -> str:
    """
    写入文件。

    Use when: 需要创建或更新文件时
    Don't use when: 写入系统敏感目录
    """
    if _is_dangerous_path(path):
        return "错误: 禁止写入敏感目录"

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, mode, encoding='utf-8') as f:
            f.write(content)
        return f"已写入: {path} ({len(content)} 字符)"
    except Exception as e:
        return f"写入错误: {str(e)}"


@tool
def list_directory(path: str = ".", pattern: str = "*") -> str:
    """
    列出目录内容。

    Use when: 需要查看目录结构时
    Don't use when: 目录不存在
    """
    if _is_dangerous_path(path):
        return "错误: 禁止访问敏感路径"

    try:
        from glob import glob
        files = glob(os.path.join(path, pattern))
        
        if not files:
            return f"目录为空: {path}"
        
        result = f"目录: {path}\n"
        for f in files:
            size = os.path.getsize(f)
            is_dir = "DIR" if os.path.isdir(f) else "FILE"
            result += f"{is_dir:6} {size:>10} {f}\n"
        
        return result
    except FileNotFoundError:
        return f"目录不存在: {path}"
    except Exception as e:
        return f"错误: {str(e)}"


@tool
def data_processor(
    operation: str,
    file_path: str,
    params: Optional[dict] = None
) -> str:
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
            return f"不支持的文件格式: {file_path}"

        if operation == "head":
            n = params.get("n", 5)
            return f"前 {n} 行:\n{df.head(n).to_string()}"

        elif operation == "describe":
            return f"数据统计:\n{df.describe().to_string()}"

        elif operation == "info":
            return f"数据信息:\n列: {list(df.columns)}\n形状: {df.shape}\n类型:\n{df.dtypes}"

        elif operation == "dropna":
            before = len(df)
            df_clean = df.dropna()
            return f"已删除 {before - len(df_clean)} 行缺失数据，剩余 {len(df_clean)} 行"

        elif operation == "groupby":
            col = params.get("group_col")
            agg_col = params.get("agg_col")
            if not col or not agg_col:
                return "错误: 需要指定 group_col 和 agg_col"
            result = df.groupby(col)[agg_col].agg(['sum', 'mean', 'count'])
            return f"分组统计:\n{result.to_string()}"

        elif operation == "filter":
            col = params.get("column")
            val = params.get("value")
            if not col:
                return "错误: 需要指定 column"
            filtered = df[df[col] == val]
            return f"筛选出 {len(filtered)} 行\n{filtered.head(10).to_string()}"

        else:
            return f"未知操作: {operation}"

    except FileNotFoundError:
        return f"文件不存在: {file_path}"
    except Exception as e:
        return f"处理错误: {str(e)}"


@tool
def search_files(path: str, pattern: str, file_type: str = "*") -> str:
    """
    搜索文件内容。

    Use when: 需要在代码库中搜索关键词时
    Don't use when: 搜索大文件或二进制文件
    """
    try:
        import re
        results = []
        
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
                except:
                    pass

        if not results:
            return f"未找到匹配: {pattern}"
        
        return f"找到 {len(results)} 处匹配:\n" + "\n".join(results[:50])

    except Exception as e:
        return f"搜索错误: {str(e)}"


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
) -> str:
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
        return f"错误: 未找到 CLI '{cli_name}'"
    if not cli.get("available"):
        return f"错误: CLI '{cli_name}' 未安装"
    if mode not in cli.get("modes", []):
        return f"错误: CLI '{cli_name}' 不支持 {mode} 模式"

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

    return json.dumps(result, ensure_ascii=False, indent=2)


@tool
def list_clis() -> str:
    """
    列出所有可用的 Coding CLI 及其状态。

    Use when: 需要了解有哪些编码工具可用时
    """
    clis = get_available_clis()
    if not clis:
        return "没有可用的 Coding CLI"

    lines = ["可用的 Coding CLI:"]
    for cli in clis:
        modes = ", ".join(cli.get("modes", []))
        caps = ", ".join(cli.get("capabilities", []))
        lines.append(f"- {cli['name']} (路径: {cli['path']})")
        lines.append(f"  模式: {modes}")
        lines.append(f"  能力: {caps}")

    return "\n".join(lines)


@tool
def list_serves() -> str:
    """
    列出所有活跃的 CLI 服务。

    Use when: 需要查看正在运行的 serve 服务时
    """
    serves = get_active_serves()
    if not serves:
        return "没有活跃的服务"

    lines = ["活跃的 CLI 服务:"]
    for s in serves:
        status = "运行中" if s["running"] else "已停止"
        lines.append(f"- {s['serve_id']} ({s['cli_name']}) - {status}")
        lines.append(f"  PID: {s['pid']}, 目录: {s['working_dir']}")
        lines.append(f"  启动时间: {s['started_at']}")

    return "\n".join(lines)


@tool
def stop_serve_tool(serve_id: str) -> str:
    """
    停止指定的 CLI 服务。

    Use when: 需要停止不再需要的 serve 服务时
    """
    result = stop_serve(serve_id)
    return json.dumps(result, ensure_ascii=False, indent=2)


@tool
def dispatch_via_acp(
    task: str,
    skill: Optional[str] = None,
    timeout: int = 300,
) -> str:
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

        return result

    except Exception as e:
        return f"Error: {str(e)}"


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
]

__all__ = ["TOOLS"]