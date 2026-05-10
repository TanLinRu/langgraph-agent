"""
Vision Engine - 屏幕截图和视觉分析

提供:
- 屏幕截图功能
- 视觉分析 (调用 LLM)
"""
import base64
import logging
import os
import subprocess
import tempfile
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class VisionEngine:
    """视觉引擎 - 屏幕截图和分析"""

    def __init__(self, screenshot_quality: int = 80):
        self.screenshot_quality = screenshot_quality

    def take_screenshot(self, region: str = "full", output_path: str = None) -> dict:
        """
        捕获屏幕截图

        Args:
            region: 截图区域 "full", "window", 或 "region"
            output_path: 输出文件路径 (可选)

        Returns:
            dict: {
                "status": "success" | "error",
                "image_path": str,  # 截图文件路径
                "base64": str,      # base64 编码的图像
                "size": dict,        # 尺寸信息
                "timestamp": str     # 时间戳
            }
        """
        try:
            import platform
            system = platform.system()

            if output_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"memory/screenshots/screenshot_{timestamp}.png"

            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            if system == "Windows":
                return self._take_screenshot_windows(output_path)
            elif system == "Darwin":
                return self._take_screenshot_macos(output_path)
            else:
                return self._take_screenshot_linux(output_path)

        except Exception as e:
            logger.error(f"[Vision] Screenshot failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    def _take_screenshot_windows(self, output_path: str) -> dict:
        """Windows 截图 - 使用 PowerShell + .NET"""
        try:
            script = f'''
Add-Type -AssemblyName System.Windows.Forms
$screen = [System.Windows.Forms.Screen]::PrimaryScreen
$bitmap = New-Object System.Drawing.Bitmap($screen.Bounds.Width, $screen.Bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($screen.Bounds.Location, [System.Drawing.Point]::Empty, $screen.Bounds.Size)
$bitmap.Save("{output_path.replace("\\", "\\\\")}", [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
'''
            subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                timeout=10
            )

            return self._get_screenshot_result(output_path)

        except Exception as e:
            return {"status": "error", "error": f"Windows screenshot failed: {e}"}

    def _take_screenshot_macos(self, output_path: str) -> dict:
        """macOS 截图 - 使用 screencapture"""
        try:
            subprocess.run(
                ["screencapture", "-x", output_path],
                capture_output=True,
                timeout=5
            )
            return self._get_screenshot_result(output_path)

        except Exception as e:
            return {"status": "error", "error": f"macOS screenshot failed: {e}"}

    def _take_screenshot_linux(self, output_path: str) -> dict:
        """Linux 截图 - 使用 gnome-screenshot 或 scrot"""
        try:
            for cmd in ["gnome-screenshot", "scrot", "import"]:
                result = subprocess.run(
                    ["which", cmd],
                    capture_output=True
                )
                if result.returncode == 0:
                    if cmd == "import":
                        subprocess.run([cmd, output_path], timeout=5)
                    else:
                        subprocess.run([cmd, "-f", "-o", output_path], timeout=5)
                    return self._get_screenshot_result(output_path)

            return {"status": "error", "error": "No screenshot tool available"}

        except Exception as e:
            return {"status": "error", "error": f"Linux screenshot failed: {e}"}

    def _get_screenshot_result(self, output_path: str) -> dict:
        """获取截图结果"""
        if not os.path.exists(output_path):
            return {"status": "error", "error": "Screenshot file not created"}

        file_size = os.path.getsize(output_path)

        with open(output_path, "rb") as f:
            base64_data = base64.b64encode(f.read()).decode("utf-8")

        return {
            "status": "success",
            "image_path": output_path,
            "base64": base64_data,
            "size": {
                "width": 0,
                "height": 0,
                "bytes": file_size
            },
            "timestamp": datetime.now().isoformat()
        }

    def analyze_screen(self, image_path: str = None, base64_image: str = None, question: str = None, llm = None) -> dict:
        """
        使用 LLM 分析屏幕内容

        Args:
            image_path: 图像文件路径
            base64_image: base64 编码的图像
            question: 分析问题
            llm: LLM 实例

        Returns:
            dict: 分析结果
        """
        if not llm:
            return {
                "status": "error",
                "error": "LLM not provided for analysis"
            }

        try:
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
            elif base64_image:
                image_base64 = base64_image
            else:
                return {"status": "error", "error": "No image provided"}

            if question is None:
                question = "Describe what's on this screen. What windows, buttons, or text are visible?"

            response = llm.invoke([
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ])

            return {
                "status": "success",
                "analysis": response.content if hasattr(response, "content") else str(response)
            }

        except Exception as e:
            logger.error(f"[Vision] Screen analysis failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }


_engine: Optional[VisionEngine] = None


def get_vision_engine(quality: int = 80) -> VisionEngine:
    """获取视觉引擎单例"""
    global _engine
    if _engine is None:
        _engine = VisionEngine(screenshot_quality=quality)
    return _engine