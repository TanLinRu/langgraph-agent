"""
Automation Module - PC 自动化

子模块:
- config: 配置定义
- vision: 截图和视觉分析
- browser: 浏览器自动化
- desktop: 桌面控制
"""
from .config import AutomationConfig, get_default_automation_config
from .vision import VisionEngine, get_vision_engine
from .browser import BrowserAutomation, BrowserConfig, get_browser_automation
from .desktop import DesktopController, DesktopConfig, get_desktop_controller

__all__ = [
    "AutomationConfig",
    "get_default_automation_config",
    "VisionEngine",
    "get_vision_engine",
    "BrowserAutomation",
    "BrowserConfig", 
    "get_browser_automation",
    "DesktopController",
    "DesktopConfig",
    "get_desktop_controller",
]