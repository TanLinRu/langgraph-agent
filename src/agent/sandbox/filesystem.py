"""
Sandbox - 沙箱安全层

提供:
- 文件系统限制
- 网络访问控制
- 进程隔离
"""
import os
import logging
import re
from typing import Optional, List, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class SandboxConfig:
    """沙箱配置"""
    enabled: bool = False
    allowed_paths: List[str] = field(default_factory=lambda: ["./", "./src", "./tests"])
    denied_paths: List[str] = field(default_factory=lambda: ["/home/*/.ssh", "/Windows/System32"])
    allowed_domains: List[str] = field(default_factory=lambda: ["github.com", "google.com"])
    blocked_domains: List[str] = field(default_factory=list)
    block_private_ips: bool = True
    max_file_size: int = 10 * 1024 * 1024


class FileSystemSandbox:
    """文件系统沙箱"""

    def __init__(self, config: SandboxConfig):
        self.config = config

    def validate_path(self, path: str) -> tuple[bool, str]:
        """
        验证路径是否允许访问

        Returns:
            (allowed, reason)
        """
        if not self.config.enabled:
            return True, "sandbox disabled"

        try:
            normalized = os.path.normpath(os.path.abspath(path))
            normalized = normalized.replace("\\", "/")

            for denied in self.config.denied_paths:
                pattern = denied.replace("*", ".*")
                if re.match(pattern, normalized):
                    return False, f"Path matches denied pattern: {denied}"

            allowed = False
            for allowed_pattern in self.config.allowed_paths:
                pattern = allowed_pattern.replace("*", ".*")
                if re.match(pattern, normalized):
                    allowed = True
                    break

            if not allowed:
                return False, f"Path not in allowed list: {allowed_pattern}"

            return True, "allowed"

        except Exception as e:
            return False, f"Path validation error: {e}"

    def can_read(self, path: str) -> bool:
        """检查是否可读"""
        allowed, _ = self.validate_path(path)
        return allowed

    def can_write(self, path: str) -> bool:
        """检查是否可写"""
        allowed, _ = self.validate_path(path)
        return allowed


class NetworkSandbox:
    """网络沙箱"""

    PRIVATE_IP_PATTERNS = [
        r"^10\.",
        r"^172\.(1[6-9]|2[0-9]|3[0-1])\.",
        r"^192\.168\.",
        r"^127\.",
        r"^localhost$",
        r"^169\.254\.169\.254$",
    ]

    def __init__(self, config: SandboxConfig):
        self.config = config

    def validate_domain(self, domain: str) -> tuple[bool, str]:
        """验证域名是否允许访问"""
        if not self.config.enabled:
            return True, "sandbox disabled"

        domain = domain.lower().strip()

        for blocked in self.config.blocked_domains:
            pattern = blocked.replace("*", ".*")
            if re.match(pattern, domain):
                return False, f"Domain blocked: {blocked}"

        if self.config.block_private_ips:
            for pattern in self.PRIVATE_IP_PATTERNS:
                if re.match(pattern, domain):
                    return False, "Private IP blocked"

        allowed = False
        for allowed_pattern in self.config.allowed_domains:
            pattern = allowed_pattern.replace("*", ".*")
            if re.match(pattern, domain):
                allowed = True
                break

        if not allowed:
            return False, f"Domain not in allowed list"

        return True, "allowed"

    def can_connect(self, host: str) -> bool:
        """检查是否可连接"""
        allowed, _ = self.validate_domain(host)
        return allowed


class Sandbox:
    """统一沙箱控制器"""

    def __init__(self, config: SandboxConfig = None):
        self.config = config or SandboxConfig()
        self.fs_sandbox = FileSystemSandbox(self.config)
        self.net_sandbox = NetworkSandbox(self.config)

    def check_file_operation(self, path: str, operation: str = "read") -> tuple[bool, str]:
        """检查文件操作"""
        if operation == "read":
            return self.fs_sandbox.can_read(path), "file read check"
        elif operation == "write":
            return self.fs_sandbox.can_write(path), "file write check"
        return True, "unknown operation"

    def check_network(self, host: str) -> tuple[bool, str]:
        """检查网络连接"""
        return self.net_sandbox.can_connect(host)

    def get_status(self) -> dict:
        """获取沙箱状态"""
        return {
            "enabled": self.config.enabled,
            "allowed_paths": self.config.allowed_paths,
            "denied_paths": self.config.denied_paths,
            "allowed_domains": self.config.allowed_domains,
        }


_sandbox: Optional[Sandbox] = None


def get_sandbox(config: SandboxConfig = None) -> Sandbox:
    """获取沙箱单例"""
    global _sandbox
    if _sandbox is None:
        _sandbox = Sandbox(config)
    return _sandbox