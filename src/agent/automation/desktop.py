"""
Desktop Control - 桌面控制 (鼠标/键盘/窗口)

提供:
- 鼠标控制
- 键盘控制
- 窗口管理
"""
import logging
import platform
import time
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DesktopConfig:
    """桌面控制配置"""
    fail_safe: bool = True
    pause: float = 0.3
    mouse_speed: int = 1


class DesktopController:
    """桌面控制器"""

    def __init__(self, config: DesktopConfig = None):
        self.config = config or DesktopConfig()
        self._pyautogui = None
        self._initialized = False

    def _init_pyautogui(self):
        """初始化 pyautogui"""
        if self._initialized:
            return

        try:
            import pyautogui
            self._pyautogui = pyautogui

            if self.config.fail_safe:
                self._pyautogui.FAILSAFE = True
            self._pyautogui.PAUSE = self.config.pause

            self._initialized = True
            logger.info("[Desktop] Initialized")

        except ImportError:
            logger.warning("[Desktop] pyautogui not installed")
            self._initialized = False
        except Exception as e:
            logger.error(f"[Desktop] Init failed: {e}")
            self._initialized = False

    def mouse_click(self, x: int = None, y: int = None, button: str = "left", clicks: int = 1) -> dict:
        """
        鼠标点击

        Args:
            x, y: 坐标 (None 表示当前位置)
            button: left, right, middle
            clicks: 点击次数
        """
        self._init_pyautogui()

        if not self._pyautogui:
            return {
                "status": "error",
                "error": "pyautogui not available"
            }

        try:
            self._pyautogui.click(x, y, clicks=clicks, button=button)
            return {
                "status": "success",
                "action": f"click_{button}",
                "position": {"x": x, "y": y},
                "clicks": clicks
            }
        except Exception as e:
            logger.error(f"[Desktop] Click failed: {e}")
            return {"status": "error", "error": str(e)}

    def mouse_move(self, x: int, y: int, duration: float = 0.0) -> dict:
        """鼠标移动"""
        self._init_pyautogui()

        if not self._pyautogui:
            return {"status": "error", "error": "pyautogui not available"}

        try:
            self._pyautogui.moveTo(x, y, duration=duration)
            return {
                "status": "success",
                "position": {"x": x, "y": y}
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def mouse_drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.5) -> dict:
        """鼠标拖拽"""
        self._init_pyautogui()

        if not self._pyautogui:
            return {"status": "error", "error": "pyautogui not available"}

        try:
            self._pyautogui.moveTo(x1, y1)
            self._pyautogui.dragTo(x2, y2, duration=duration)
            return {
                "status": "success",
                "from": {"x": x1, "y": y1},
                "to": {"x": x2, "y": y2}
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def keyboard_type(self, text: str, interval: float = None) -> dict:
        """键盘输入文本"""
        self._init_pyautogui()

        if not self._pyautogui:
            return {"status": "error", "error": "pyautogui not available"}

        try:
            self._pyautogui.write(text, interval=interval)
            return {
                "status": "success",
                "text": text,
                "length": len(text)
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def keyboard_press(self, key: str) -> dict:
        """按键按下"""
        self._init_pyautogui()

        if not self._pyautogui:
            return {"status": "error", "error": "pyautogui not available"}

        try:
            self._pyautogui.press(key)
            return {
                "status": "success",
                "key": key
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def keyboard_hotkey(self, *keys) -> dict:
        """快捷键"""
        self._init_pyautogui()

        if not self._pyautogui:
            return {"status": "error", "error": "pyautogui not available"}

        try:
            self._pyautogui.hotkey(*keys)
            return {
                "status": "success",
                "keys": list(keys)
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def scroll(self, direction: str = "down", amount: int = 3) -> dict:
        """滚动"""
        self._init_pyautogui()

        if not self._pyautogui:
            return {"status": "error", "error": "pyautogui not available"}

        try:
            clicks = amount if direction == "down" else -amount
            self._pyautogui.scroll(clicks)
            return {
                "status": "success",
                "direction": direction,
                "amount": amount
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_screen_size(self) -> dict:
        """获取屏幕尺寸"""
        self._init_pyautogui()

        if not self._pyautogui:
            return {"width": 1920, "height": 1080}

        size = self._pyautogui.size()
        return {
            "width": size.width,
            "height": size.height
        }

    def get_current_position(self) -> dict:
        """获取当前鼠标位置"""
        self._init_pyautogui()

        if not self._pyautogui:
            return {"x": 0, "y": 0}

        pos = self._pyautogui.position()
        return {"x": pos.x, "y": pos.y}


_desktop_controller: Optional[DesktopController] = None


def get_desktop_controller(config: DesktopConfig = None) -> DesktopController:
    """获取桌面控制器单例"""
    global _desktop_controller
    if _desktop_controller is None:
        _desktop_controller = DesktopController(config)
    return _desktop_controller