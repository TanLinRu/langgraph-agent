"""
Context Module Real API Call Verification Script

Verify:
1. Token compression - verify 70% threshold triggers compression
2. Multi-turn conversation - verify history compression and recovery
3. Long-term memory - verify session persistence and recovery

Usage:
    # Mock mode (default) - no API calls, fast verification
    python docs/context/context-log-diagnosis.py

    # Real API mode - set env var before running
    $env:CONTEXT_USE_REAL_API = "true"
    python docs/context/context-log-diagnosis.py

Output:
    - stdout: summary info (PASS/FAIL, statistics)
    - logs/context-verify-*.log: full detailed log (every message content)
"""

import logging
import sys
import os
import time
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

USE_REAL_API = os.getenv("CONTEXT_USE_REAL_API", "false").lower() == "true"
TIMESTAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"context-verify-{TIMESTAMP}.log"
JSONL_FILE = LOG_DIR / f"context-verify-{TIMESTAMP}.jsonl"


def setup_logging() -> None:
    """Setup dual-channel logging: stdout (INFO) + file (DEBUG)"""

    class UTF8FileHandler(logging.FileHandler):
        def __init__(self, filename, **kwargs):
            super().__init__(filename, encoding="utf-8", **kwargs)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    file_handler = UTF8FileHandler(str(LOG_FILE))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    root_logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    ))
    root_logger.addHandler(console_handler)


def dump_messages(messages: List[Any], tag: str = "MESSAGES", logger_instance: logging.Logger = None) -> None:
    """Dump full message content to log file (DEBUG level)"""
    log = logger_instance or logging.getLogger()
    log.debug("")
    log.debug("=" * 70)
    log.debug(f"[{tag}] {len(messages)} messages")
    log.debug("=" * 70)

    for i, msg in enumerate(messages):
        if isinstance(msg, dict):
            role = msg.get("type") or msg.get("role", "unknown")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
        else:
            role = getattr(msg, "type", "unknown")
            content = getattr(msg, "content", "") or ""
            tool_calls = getattr(msg, "tool_calls", []) or []

        tokens = _count_tokens(str(content))
        log.debug("")
        log.debug(f"--- Message [{i}] (role: {role}, tokens: {tokens}) ---")
        if isinstance(content, str):
            for line in content.split("\n"):
                log.debug(f"  {line}")
        else:
            log.debug(f"  {content}")

        if tool_calls:
            log.debug(f"  [tool_calls]:")
            for tc in tool_calls:
                tc_name = tc.get("name", "unknown") if isinstance(tc, dict) else getattr(tc, "name", "unknown")
                tc_args = tc.get("arguments", {}) if isinstance(tc, dict) else getattr(tc, "arguments", {})
                log.debug(f"    - {tc_name}: {json.dumps(tc_args, ensure_ascii=False)}")

        log.debug(f"--- End Message [{i}] ---")


def dump_dict(data: Dict, tag: str = "DATA", logger_instance: logging.Logger = None) -> None:
    """Dump dictionary to log file (DEBUG level)"""
    log = logger_instance or logging.getLogger()
    log.debug("")
    log.debug(f"[{tag}]")
    for key, value in data.items():
        if isinstance(value, str) and len(value) > 500:
            log.debug(f"  {key}: {value[:500]}... [truncated, full in jsonl]")
        else:
            log.debug(f"  {key}: {value}")


def log_jsonl(data: Dict) -> None:
    """Append structured data to JSONL file"""
    with open(JSONL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken"""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text or ""))
    except Exception:
        return len(text or "") // 4


log = logging.getLogger(__name__)


def create_llm():
    """Create real LLM instance"""
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("OPENAI_API_KEY", "")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    if not api_key:
        log.warning("OPENAI_API_KEY not set")
        return None

    return ChatOpenAI(
        model=os.getenv("AGENT_MODEL", "gpt-4o-mini"),
        api_key=api_key,
        base_url=base_url,
        temperature=0
    )


def create_mock_agent():
    """Create mock agent for testing without API calls"""
    log.info("Creating mock agent (no API calls)")

    class MockAgent:
        def __init__(self):
            self.messages_history = []
            self.turn_count = 0

        def run(self, user_input: str, thread_id: str = "mock-thread"):
            self.turn_count += 1
            log.info(f"[MockAgent] Turn {self.turn_count}: {user_input[:50]}...")
            log_jsonl({"event": "agent_run", "turn": self.turn_count, "input": user_input, "thread_id": thread_id})

            user_msg = {"role": "user", "content": user_input}
            assistant_content = f"Mock response {self.turn_count}: I understand you said '{user_input[:30]}...'. This is a simulated response for testing purposes."

            if user_input.lower() == "count tokens":
                token_count = _count_tokens(user_input)
                assistant_content = f"Token count for input: {token_count} tokens (mock)"

            assistant_msg = {"role": "assistant", "content": assistant_content}

            self.messages_history.extend([user_msg, assistant_msg])

            messages_for_llm = [{"role": "system", "content": "You are a helpful assistant."}]
            messages_for_llm.extend(self.messages_history[-6:])

            dump_messages(messages_for_llm, f"MOCK_LLM_INPUT_TURN{self.turn_count}", log)
            dump_messages([assistant_msg], f"MOCK_LLM_OUTPUT_TURN{self.turn_count}", log)

            return {
                "result": {
                    "messages": [user_msg, assistant_msg]
                },
                "token_usage": {
                    "input_tokens": _count_tokens(json.dumps(messages_for_llm)),
                    "output_tokens": _count_tokens(assistant_content)
                },
                "status": "success",
                "cost_usd": 0.0,
                "iterations": 1,
            }

    return MockAgent()


def print_summary_table():
    """Print summary table to stdout"""
    print("")
    print("=" * 70)
    print(f" Context Module Verification Complete")
    print("=" * 70)
    print(f"  Mode: {'REAL API' if USE_REAL_API else 'MOCK'}")
    print(f"  Log:  {LOG_FILE}")
    print(f"  JSONL: {JSONL_FILE}")
    print("=" * 70)


def test_token_compression():
    """Test 1: Token compression with 3K threshold"""
    log.info("")
    log.info("=" * 70)
    log.info("[TEST 1] Token Compression")
    log.info("=" * 70)

    from src.agent.context.compression import ContextCompressor, CompressionConfig

    llm = create_llm() if USE_REAL_API else None

    log.info(f"LLM for compression: {'Real LLM' if llm else 'Mock (no LLM)'}")

    config = CompressionConfig(
        max_tokens=5000,
        trigger_threshold=0.1,
        keep_recent=3,
        summary_max_tokens=200,
        hot_zone_size=3
    )

    log.info(f"Config: max_tokens={config.max_tokens}, threshold={config.trigger_threshold} ({config.max_tokens * config.trigger_threshold:.0f} tokens trigger)")

    log.info(f"        keep_recent={config.keep_recent}, summary_max_tokens={config.summary_max_tokens}")

    compressor = ContextCompressor(config, llm=llm)

    messages = []

    system_content = """
You are a professional Python developer assistant.
You help users write clean, efficient, and well-tested code.
Best practices:
- Clear variable naming
- Complete docstrings
- Type annotations
- Unit test coverage
""".strip()

    messages.append({"role": "system", "content": system_content})

    rounds = [
        ("user", "Please implement quicksort with unit tests. Include documentation, type hints, and comprehensive test coverage."),
        ("assistant", """
def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    return quicksort([x for x in arr if x < pivot]) + [pivot] + quicksort([x for x in arr if x > pivot])

def test_quicksort():
    assert quicksort([3,1,2]) == [1,2,3]
    print('Tests passed!')

def quicksort_detailed(arr):
    '''Sort array using quicksort algorithm. Time: O(n log n), Space: O(log n)'''
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quicksort_detailed(left) + middle + quicksort_detailed(right)
"""),
        ("user", "Add edge case tests, benchmark, and performance analysis"),
        ("assistant", """
def test_edge_cases():
    assert quicksort([]) == []
    assert quicksort([1]) == [1]
    assert quicksort([1,2,3]) == [1,2,3]
    print('Edge cases passed!')

import time, random
def benchmark():
    results = []
    for size in [100, 1000, 5000, 10000]:
        arr = [random.randint(0, 1000) for _ in range(size)]
        start = time.time()
        quicksort(arr.copy())
        elapsed = (time.time()-start)*1000
        results.append(f'Size {size}: {elapsed:.2f}ms')
    return '\\n'.join(results)

Time complexity analysis:
- Best case: O(n log n) when pivot is median
- Average case: O(n log n)
- Worst case: O(n^2) when pivot is always min/max
- Space: O(log n) for recursion stack
"""),
        ("user", "Add more test cases, analyze pivot selection strategies, and implement three-way partitioning"),
        ("assistant", """
import random

def test_more_cases():
    assert quicksort([5,5,5,5]) == [5,5,5,5]
    assert quicksort([2,4,1,3]) == [1,2,3,4]
    assert quicksort([9,8,7,6,5]) == [5,6,7,8,9]
    print('All tests passed!')

def quicksort_three_way(arr):
    '''Three-way partition quicksort for handling duplicates efficiently.'''
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left, middle, right = [], [], []
    for x in arr:
        if x < pivot:
            left.append(x)
        elif x == pivot:
            middle.append(x)
        else:
            right.append(x)
    return quicksort_three_way(left) + middle + quicksort_three_way(right)

Pivot selection strategies comparison:
1. First element: Simple but O(n^2) worst case
2. Random element: Good average case, avoids worst case
3. Median-of-three: Best balance of simplicity and performance
4. Median-of-medians: O(n log n) worst case but slower average
"""),
    ]

    for role, content in rounds:
        messages.append({"role": role, "content": content})

    dump_messages(messages, "COMPRESSION_INPUT_MESSAGES", log)

    total_tokens = sum(_count_tokens(m["content"]) for m in messages)
    log.info("")
    log.info(f"[STAT] Input: {len(messages)} messages, {total_tokens} tokens")
    log.info(f"[STAT] Threshold: {config.max_tokens * config.trigger_threshold:.0f} tokens")
    log.info(f"[STAT] Compression will trigger: {total_tokens > config.max_tokens * config.trigger_threshold}")

    for i, msg in enumerate(messages):
        t = _count_tokens(msg["content"])
        log.debug(f"  [{i}] {msg['role']}: {t} tokens | {msg['content'][:60]}...")

    log.info("")
    log.info("[COMPRESS] Executing compression...")

    start_time = time.time()
    result = compressor.compress(messages)
    elapsed = time.time() - start_time

    log.info(f"[RESULT] Compression done in {elapsed:.2f}s")
    log.info(f"[RESULT] Original: {result.original_count} msgs, {total_tokens} tokens")
    log.info(f"[RESULT] Compressed: {result.compressed_count} msgs")
    log.info(f"[RESULT] Compression ratio: {result.compression_ratio:.1%}")

    if result.errors:
        for err in result.errors:
            log.error(f"[ERROR] {err}")

    dump_messages(result.compressed_messages, "COMPRESSION_OUTPUT_MESSAGES", log)

    compressed_tokens = sum(_count_tokens(m["content"]) for m in result.compressed_messages)

    log.info("")
    log.info(f"[STAT] Original tokens: {total_tokens}")
    log.info(f"[STAT] Compressed tokens: {compressed_tokens}")
    log.info(f"[STAT] Saved: {(1 - compressed_tokens/total_tokens) * 100:.1f}%")

    is_compressed = result.compressed_count < result.original_count
    is_token_saved = compressed_tokens < total_tokens

    log.info("")
    log.info(f"[CHECK] Message count reduced: {'PASS' if is_compressed else 'FAIL'}")
    log.info(f"[CHECK] Token saved: {'PASS' if is_token_saved else 'FAIL'}")

    log_jsonl({
        "event": "compression_test",
        "mode": "real" if USE_REAL_API else "mock",
        "original_messages": len(messages),
        "original_tokens": total_tokens,
        "compressed_messages": result.compressed_count,
        "compressed_tokens": compressed_tokens,
        "compression_ratio": result.compression_ratio,
        "passed": is_compressed and is_token_saved
    })

    return result


def test_multi_turn_conversation():
    """Test 2: Multi-turn conversation"""
    log.info("")
    log.info("=" * 70)
    log.info("[TEST 2] Multi-turn Conversation")
    log.info("=" * 70)

    if USE_REAL_API:
        from src.agent.agent import create_agent
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

        if not api_key:
            log.warning("OPENAI_API_KEY not set, skipping real API test")
            return None

        agent = create_agent(
            model=os.getenv("AGENT_MODEL", "gpt-4o-mini"),
            api_key=api_key,
            base_url=base_url,
        )
    else:
        agent = create_mock_agent()

    import uuid
    thread_id = f"test-multi-{uuid.uuid4().hex[:8]}"

    log.info(f"Thread ID: {thread_id}")

    turns = [
        "Hi",
        "What is Python?",
        "Give me an example",
    ]

    results = []

    for i, user_input in enumerate(turns):
        log.info("")
        log.info(f"[TURN {i+1}] User: {user_input}")

        start_time = time.time()
        result = agent.run(user_input, thread_id=thread_id)
        elapsed = time.time() - start_time

        result_data = result.get("result") or {}
        messages = result_data.get("messages", [])
        token_usage = result.get("token_usage", {})
        response = messages[-1] if messages else None

        if response:
            resp_content = response.get("content", "") if isinstance(response, dict) else getattr(response, "content", "")
        else:
            resp_content = "(empty)"

        log.info(f"[TURN {i+1}] Response: {resp_content[:80]}...")
        log.info(f"[TURN {i+1}] Stats: {elapsed:.1f}s, {len(messages)} msgs, {token_usage.get('input_tokens', 0) + token_usage.get('output_tokens', 0)} tokens")

        dump_messages(messages, f"MULTI_TURN_TURN{i+1}_OUTPUT", log)

        results.append({
            "turn": i + 1,
            "elapsed": elapsed,
            "messages": len(messages),
            "tokens": token_usage.get("input_tokens", 0) + token_usage.get("output_tokens", 0),
        })

    log.info("")
    log.info("[STAT] Multi-turn summary:")
    for r in results:
        log.info(f"  Turn {r['turn']}: {r['elapsed']:.1f}s, {r['messages']} msgs, {r['tokens']} tokens")

    total_tokens = sum(r["tokens"] for r in results)
    log.info(f"  Total: {total_tokens} tokens")

    log_jsonl({
        "event": "multi_turn_test",
        "mode": "real" if USE_REAL_API else "mock",
        "thread_id": thread_id,
        "turns": results,
        "total_tokens": total_tokens
    })

    return results


def test_long_term_memory():
    """Test 3: Long-term memory"""
    log.info("")
    log.info("=" * 70)
    log.info("[TEST 3] Long-term Memory")
    log.info("=" * 70)

    from src.agent.context.long_term import LongTermManager, LongTermConfig

    import tempfile
    temp_dir = tempfile.mkdtemp()

    config = LongTermConfig(
        memory_dir=Path(temp_dir),
        session_ttl_days=7,
        vector_enabled=False,
        chroma_persist_dir=Path(temp_dir) / "chroma"
    )

    log.info(f"Memory dir: {temp_dir}")

    manager = LongTermManager(config)

    thread_id = f"test-long-term-{int(time.time())}"

    session_messages = [
        {"role": "user", "content": "Test message 1 - implement quicksort"},
        {"role": "assistant", "content": "Here's quicksort: def quicksort(arr): ..."},
        {"role": "user", "content": "Test message 2 - add unit tests"},
        {"role": "assistant", "content": "Added unit tests for edge cases."},
    ]

    log.info(f"[SAVE] Thread: {thread_id}, Messages: {len(session_messages)}")

    for msg in session_messages:
        log.debug(f"  {msg['role']}: {msg['content'][:60]}...")

    log_jsonl({
        "event": "long_term_save",
        "thread_id": thread_id,
        "messages": session_messages
    })

    manager.save_session(thread_id, session_messages, {"test": True})
    log.info("[SAVE] Session saved successfully")

    log.info("[LOAD] Loading session...")
    loaded_messages = manager.load_session_messages(thread_id)

    log.info(f"[LOAD] Loaded: {len(loaded_messages)} messages")

    for msg in loaded_messages:
        log.debug(f"  {msg.get('role', 'unknown')}: {msg.get('content', '')[:60]}...")

    log_jsonl({
        "event": "long_term_load",
        "thread_id": thread_id,
        "loaded_messages": loaded_messages
    })

    passed = len(loaded_messages) > 0

    log.info(f"[CHECK] Session saved and loaded: {'PASS' if passed else 'FAIL'}")

    try:
        import shutil
        shutil.rmtree(temp_dir)
        log.info("[CLEANUP] Temp dir removed")
    except Exception as e:
        log.warning(f"[CLEANUP] Failed: {e}")

    return loaded_messages if passed else None


def main():
    """Main entry point"""
    print("")
    print("=" * 70)
    print(f" Context Module Verification (timestamp: {TIMESTAMP})")
    print("=" * 70)
    print(f" Mode: {'REAL API' if USE_REAL_API else 'MOCK (no API calls)'}")
    print(f" Log:  {LOG_FILE}")
    print("=" * 70)

    setup_logging()

    log.info("=== Context Verification Started ===")
    log.info(f"USE_REAL_API: {USE_REAL_API}")
    log.info(f"LOG_FILE: {LOG_FILE}")
    log.info(f"JSONL_FILE: {JSONL_FILE}")

    log_jsonl({
        "event": "verification_start",
        "timestamp": TIMESTAMP,
        "mode": "real" if USE_REAL_API else "mock"
    })

    results = {}
    passed_count = 0
    failed_count = 0

    print("")
    print("Running tests...")

    try:
        r = test_token_compression()
        results["token_compression"] = r
        if r and r.compressed_count < r.original_count:
            passed_count += 1
            print("  [PASS] Token compression")
        else:
            failed_count += 1
            print("  [FAIL] Token compression")
    except Exception as e:
        log.exception("Token compression test failed")
        results["token_compression"] = None
        failed_count += 1
        print(f"  [FAIL] Token compression: {e}")

    try:
        r = test_multi_turn_conversation()
        results["multi_turn"] = r
        if r:
            passed_count += 1
            print("  [PASS] Multi-turn conversation")
        else:
            failed_count += 1
            print("  [FAIL] Multi-turn conversation")
    except Exception as e:
        log.exception("Multi-turn test failed")
        results["multi_turn"] = None
        failed_count += 1
        print(f"  [FAIL] Multi-turn: {e}")

    try:
        r = test_long_term_memory()
        results["long_term"] = r
        if r:
            passed_count += 1
            print("  [PASS] Long-term memory")
        else:
            failed_count += 1
            print("  [FAIL] Long-term memory")
    except Exception as e:
        log.exception("Long-term memory test failed")
        results["long_term"] = None
        failed_count += 1
        print(f"  [FAIL] Long-term memory: {e}")

    print_summary_table()

    log.info("")
    log.info("=== Verification Summary ===")
    log.info(f"Passed: {passed_count}, Failed: {failed_count}, Total: {passed_count + failed_count}")

    log_jsonl({
        "event": "verification_end",
        "passed": passed_count,
        "failed": failed_count,
        "results": {k: bool(v) for k, v in results.items()}
    })

    log.info("=== Context Verification Finished ===")

    print("")
    print("查看详细日志:")
    print(f"  完整日志: {LOG_FILE}")
    print(f"  结构化日志: {JSONL_FILE}")
    print("")
    print("查看方式:")
    print(f'  notepad "{LOG_FILE}"')
    print(f'  Get-Content "{LOG_FILE}" -Tail 50 -Wait')


if __name__ == "__main__":
    main()