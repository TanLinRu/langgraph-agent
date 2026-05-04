import argparse
import asyncio
import os
import sys
import logging
from pathlib import Path

from .agent import create_agent
from .config import DEFAULT_CONFIG
from dotenv import load_dotenv

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_message_content(msg):
    """提取消息内容，兼容 dict 和 LangChain AIMessage"""
    if isinstance(msg, dict):
        return msg.get("content", "")
    return getattr(msg, "content", str(msg))


def main():
    config = DEFAULT_CONFIG.model_copy(update={
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    })

    parser = argparse.ArgumentParser(description="LangGraph Agent")
    parser.add_argument("--model", default=config.model, help="Model name")
    parser.add_argument("--input", "-i", help="Input text")
    parser.add_argument("--interactive", "-it", action="store_true", help="Interactive mode")
    parser.add_argument("--archive", action="store_true", help="Run archive")
    parser.add_argument("--acp", action="store_true", help="Run ACP server (stdio JSON-RPC)")
    args = parser.parse_args()

    if not config.api_key:
        logger.error("请设置 OPENAI_API_KEY 环境变量或 .env 文件")
        return

    if args.acp:
        from .acp_server import main as acp_main
        asyncio.run(acp_main())
        return

    if not config.api_key:
        logger.error("请设置 OPENAI_API_KEY 环境变量或 .env 文件")
        return

    agent = create_agent(
        model=args.model,
        api_key=config.api_key,
        base_url=config.base_url
    )

    if args.archive:
        result = agent.archive()
        print(result)
        return

    if args.interactive:
        print("欢迎使用 LangGraph Agent (输入 'quit' 退出)")
        thread_id = "interactive"

        while True:
            user_input = input("\n> ")
            if user_input.lower() in ["quit", "exit"]:
                break

            result = agent.run(user_input, thread_id=thread_id)
            if result["status"] == "success":
                messages = result["result"].get("messages", [])
                if messages:
                    last = messages[-1]
                    print(f"\n{get_message_content(last)}")
            else:
                print(f"错误: {result.get('error')}")

        agent.close()
        return

    if args.input:
        result = agent.run(args.input)
        if result["status"] == "success":
            messages = result["result"].get("messages", [])
            if messages:
                last = messages[-1]
                print(get_message_content(last))

            # 打印指标
            metrics = agent.get_metrics()
            print("\n--- 指标统计 ---")
            print(f"请求次数: {metrics['total_requests']}")
            print(f"Token 消耗: {metrics['total_tokens']}")
            print(f"预估成本: ${metrics['total_cost_usd']}")
            print(f"总耗时: {metrics['total_latency_sec']}s")
            print(f"平均耗时: {metrics['avg_latency_sec']}s")
        else:
            print(f"错误: {result.get('error')}")
        agent.close()
        return

    parser.print_help()


if __name__ == "__main__":
    main()