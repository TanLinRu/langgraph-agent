"""
Coding CLI 注册表与自动检测

支持的外部 Coding CLI：
- opencode: Agent Client Protocol, run/serve 模式
- claude: Claude Code CLI
"""
import shutil
from typing import Optional

CLI_REGISTRY: dict = {}


def _detect_cli(name: str, commands: list[str]) -> dict:
    """检测 CLI 是否可用"""
    for cmd in commands:
        path = shutil.which(cmd)
        if path:
            return {"name": name, "path": path, "available": True}
    return {"name": name, "path": None, "available": False}


def _get_opencode_info() -> dict:
    """获取 opencode 详细信息"""
    info = _detect_cli("opencode", ["opencode"])
    if not info["available"]:
        return info

    info.update({
        "modes": ["run", "serve"],
        "capabilities": ["code", "test", "debug", "refactor", "review"],
        "auto_approve_flag": "--dangerously-skip-permissions",
        "json_output_flag": "--format json",
        "session_flag": "-s",
        "continue_flag": "-c",
        "model_flag": "-m",
        "dir_flag": "--dir",
        "serve_port_flag": "--port",
        "default_model": None,
        "description": "AI 编码代理，支持 run（同步任务）和 serve（持久服务）两种模式",
    })
    return info


def _get_claude_info() -> dict:
    """获取 Claude Code 详细信息"""
    info = _detect_cli("claude", ["claude"])
    if not info["available"]:
        return info

    info.update({
        "modes": ["run"],
        "capabilities": ["code", "test", "debug", "refactor"],
        "auto_approve_flag": "--dangerously-skip-permissions",
        "json_output_flag": "--output-format json",
        "description": "Claude Code CLI，Anthropic 官方编码代理",
    })
    return info


def detect_all_clis() -> dict:
    """检测所有可用的 Coding CLI"""
    clis = {}
    for getter in [_get_opencode_info, _get_claude_info]:
        info = getter()
        clis[info["name"]] = info
    return clis


def get_cli(name: str) -> Optional[dict]:
    """获取指定 CLI 信息"""
    if not CLI_REGISTRY:
        CLI_REGISTRY.update(detect_all_clis())
    return CLI_REGISTRY.get(name)


def get_available_clis() -> list[dict]:
    """获取所有可用的 CLI 列表"""
    if not CLI_REGISTRY:
        CLI_REGISTRY.update(detect_all_clis())
    return [cli for cli in CLI_REGISTRY.values() if cli.get("available")]


def init():
    """初始化 CLI 注册表"""
    CLI_REGISTRY.update(detect_all_clis())
    return CLI_REGISTRY


__all__ = [
    "CLI_REGISTRY",
    "detect_all_clis",
    "get_cli",
    "get_available_clis",
    "init",
]
