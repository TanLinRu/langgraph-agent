"""
Automation Configuration - PC 自动化配置
"""
from pydantic import BaseModel, Field
from typing import Optional


class AutomationConfig(BaseModel):
    """自动化功能配置"""

    enabled: bool = Field(
        default=False,
        description="是否启用 PC 自动化功能"
    )

    browser_use_enabled: bool = Field(
        default=True,
        description="是否启用浏览器自动化"
    )

    desktop_control_enabled: bool = Field(
        default=True,
        description="是否启用桌面控制"
    )

    screenshot_quality: int = Field(
        default=80,
        ge=10,
        le=100,
        description="截图质量 (10-100)"
    )

    sandbox_mode: str = Field(
        default="os-native",
        description="沙箱模式: os-native, docker, disabled"
    )

    allowed_apps: list[str] = Field(
        default_factory=list,
        description="允许操作的应用列表"
    )

    hitl_required: bool = Field(
        default=True,
        description="敏感操作是否需要人工审批"
    )

    browser_allowed_domains: list[str] = Field(
        default_factory=lambda: ["github.com", "google.com", "bing.com"],
        description="浏览器允许访问的域名"
    )

    browser_blocked_domains: list[str] = Field(
        default_factory=lambda: ["*.internal.corp.com"],
        description="浏览器禁止访问的域名"
    )

    desktop_allowed_paths: list[str] = Field(
        default_factory=lambda: ["./", "./src", "./tests", "./docs", "./ui"],
        description="桌面控制允许的文件路径"
    )

    max_actions_per_minute: int = Field(
        default=60,
        description="每分钟最大操作数"
    )

    screenshot_timeout: int = Field(
        default=10,
        description="截图超时时间(秒)"
    )


def get_default_automation_config() -> AutomationConfig:
    """获取默认自动化配置"""
    return AutomationConfig()