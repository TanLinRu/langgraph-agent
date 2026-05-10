"""
Browser Automation - 基于 browser-use 的浏览器自动化

提供:
- 浏览器导航和控制
- 元素交互
- 网页内容提取
"""
import asyncio
import logging
from typing import Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class BrowserConfig:
    """浏览器配置"""
    headless: bool = True
    allowed_domains: list[str] = field(default_factory=lambda: ["github.com", "google.com"])
    blocked_domains: list[str] = field(default_factory=list)
    max_iframes: int = 100
    wait_network_idle: float = 2.0
    use_vision: bool = False


class BrowserAutomation:
    """浏览器自动化控制器"""

    def __init__(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self._agent = None
        self._browser = None
        self._initialized = False

    async def initialize(self):
        """初始化浏览器"""
        if self._initialized:
            return

        try:
            from browser_use import Browser, BrowserProfile

            browser_profile = BrowserProfile()
            if self.config.allowed_domains:
                browser_profile.allowed_domains = self.config.allowed_domains
            if self.config.blocked_domains:
                browser_profile.blocked_domains = self.config.blocked_domains

            self._browser = Browser(
                headless=self.config.headless,
                browser_profile=browser_profile,
                max_iframes=self.config.max_iframes,
                wait_for_network_idle_page_load_time=self.config.wait_network_idle,
            )

            self._initialized = True
            logger.info("[Browser] Initialized")

        except ImportError:
            logger.warning("[Browser] browser-use not installed, using fallback")
            self._initialized = False
        except Exception as e:
            logger.error(f"[Browser] Init failed: {e}")
            self._initialized = False

    async def navigate(self, url: str) -> dict:
        """导航到 URL"""
        if not self._initialized:
            await self.initialize()

        if not self._browser:
            return {
                "status": "error",
                "error": "Browser not available (browser-use may not be installed)",
                "fallback": "Install with: pip install browser-use"
            }

        try:
            from browser_use import Agent, ChatOpenAI

            llm = ChatOpenAI(model="gpt-4o")
            agent = Agent(
                task=f"Navigate to {url} and confirm the page loaded",
                llm=llm,
                browser=self._browser,
                max_actions_per_step=1,
            )

            history = await agent.run()

            return {
                "status": "success",
                "url": url,
                "final_result": history.final_result,
                "steps": len(history.history),
            }

        except Exception as e:
            logger.error(f"[Browser] Navigation failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def snapshot(self) -> dict:
        """获取当前页面快照"""
        if not self._browser:
            return {
                "status": "error",
                "error": "Browser not initialized"
            }

        try:
            from browser_use import Agent, Browser, ChatOpenAI

            agent = Agent(
                task="Extract the page content and structure",
                llm=ChatOpenAI(model="gpt-4o"),
                browser=self._browser,
            )

            history = await agent.run()

            return {
                "status": "success",
                "content": history.final_result,
            }

        except Exception as e:
            logger.error(f"[Browser] Snapshot failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def execute_task(self, task: str, llm=None) -> dict:
        """执行浏览器任务"""
        if not self._initialized:
            await self.initialize()

        if not self._browser or not llm:
            return {
                "status": "error",
                "error": "Browser or LLM not available"
            }

        try:
            from browser_use import Agent

            agent = Agent(
                task=task,
                llm=llm,
                browser=self._browser,
            )

            history = await agent.run()

            return {
                "status": "success",
                "result": history.final_result,
                "actions": len(history.history),
            }

        except Exception as e:
            logger.error(f"[Browser] Task failed: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def close(self):
        """关闭浏览器"""
        if self._browser:
            try:
                await self._browser.close()
                self._initialized = False
            except Exception as e:
                logger.warning(f"[Browser] Close error: {e}")


_browser_automation: Optional[BrowserAutomation] = None


def get_browser_automation(config: BrowserConfig = None) -> BrowserAutomation:
    """获取浏览器自动化单例"""
    global _browser_automation
    if _browser_automation is None:
        _browser_automation = BrowserAutomation(config)
    return _browser_automation