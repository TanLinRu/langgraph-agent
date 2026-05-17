"""自定义测试日志输出插件"""

import pytest
import os
import sys
import time
from collections import defaultdict


class ResultCollector:
    """测试结果收集器"""

    def __init__(self):
        self.stats = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0, "error": 0})
        self.start_time = None
        self.end_time = None
        self.failed_tests = []

    def collect_result(self, item, status: str):
        """收集测试结果"""
        markers = [m.name for m in item.iter_markers()]

        if markers:
            for marker in markers:
                if marker in ["unit", "integration", "e2e", "mock", "real_api", "context", "agent", "tools", "slow"]:
                    self.stats[marker][status] += 1

        self.stats["total"][status] += 1


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """配置阶段 - 初始化"""
    config._test_summary = ResultCollector()
    config._test_summary.start_time = time.time()

    print("\n" + "=" * 70)
    print("  LangGraph Agent Test Suite")
    print("=" * 70)
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  Platform: {sys.platform}")
    print(f"  Test Paths: {config.getoption('testpaths')}")
    print(f"  Mode: {'REAL_API' if os.getenv('USE_REAL_API') else 'MOCK'}")
    print("=" * 70 + "\n")


@pytest.hookimpl(trylast=True)
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """测试结束 - 输出汇总"""
    if not hasattr(config, "_test_summary"):
        return

    summary = config._test_summary
    summary.end_time = time.time()
    duration = summary.end_time - summary.start_time

    terminalreporter.write_sep("=", "测试执行摘要")

    terminalreporter.write_line("")
    terminalreporter.write_line(f"{'类别':<20} {'通过':>8} {'失败':>8} {'跳过':>8} {'错误':>8} {'总计':>8}")
    terminalreporter.write_line("-" * 70)

    exclude_keys = {"total"}
    categories = {k: v for k, v in summary.stats.items() if k not in exclude_keys}

    for category in ["unit", "integration", "e2e", "mock", "real_api", "slow", "context", "agent", "tools"]:
        if category in categories:
            stats = categories[category]
            passed = stats["passed"]
            failed = stats["failed"]
            skipped = stats["skipped"]
            error = stats["error"]
            total = passed + failed + skipped + error

            if failed > 0 or error > 0:
                color = "red"
            elif skipped > 0:
                color = "yellow"
            else:
                color = "green"

            terminalreporter.write_line(
                f"{category:<20} {passed:>8} {failed:>8} {skipped:>8} {error:>8} {total:>8}",
                ** {color: True}
            )

    for category, stats in sorted(categories.items()):
        if category in ["unit", "integration", "e2e", "mock", "real_api", "slow", "context", "agent", "tools"]:
            continue
        passed = stats["passed"]
        failed = stats["failed"]
        skipped = stats["skipped"]
        error = stats["error"]
        total = passed + failed + skipped + error

        if failed > 0 or error > 0:
            color = "red"
        elif skipped > 0:
            color = "yellow"
        else:
            color = "green"

        terminalreporter.write_line(
            f"{category:<20} {passed:>8} {failed:>8} {skipped:>8} {error:>8} {total:>8}",
            **{color: True}
        )

    total_stats = summary.stats.get("total", {})
    terminalreporter.write_line("-" * 70)
    terminalreporter.write_line(
        f"{'总计':<20} {total_stats.get('passed', 0):>8} {total_stats.get('failed', 0):>8} "
        f"{total_stats.get('skipped', 0):>8} {total_stats.get('error', 0):>8} "
        f"{sum(total_stats.values()):>8}",
        bold=True
    )

    terminalreporter.write_line("")
    terminalreporter.write_line(f"执行时间: {duration:.2f}s")
    terminalreporter.write_line(f"测试模式: {'REAL_API' if os.getenv('USE_REAL_API') else 'MOCK'}")
    terminalreporter.write_line("")

    failed_items = terminalreporter.stats.get("failed", [])
    error_items = terminalreporter.stats.get("error", [])

    if failed_items or error_items:
        terminalreporter.write_sep("=", "失败测试详情", red=True)
        for test in failed_items + error_items:
            terminalreporter.write_line(f"  FAIL: {test.nodeid}", red=True)
            if hasattr(test, "longrepr") and test.longrepr:
                try:
                    terminalreporter.write_line(f"    {test.longrepr}", red=True)
                except:
                    pass
        terminalreporter.write_line("")

    skipped_items = terminalreporter.stats.get("skipped", [])
    if skipped_items:
        terminalreporter.write_sep("=", "跳过测试", yellow=True)
        unique_skips = {}
        for test in skipped_items:
            reason = getattr(test, "longrepr", "未知原因")
            if reason not in unique_skips:
                unique_skips[reason] = []
            unique_skips[reason].append(test.nodeid.split("::")[-1])

        for reason, tests in unique_skips.items():
            terminalreporter.write_line(f"  原因: {reason}", yellow=True)
            for test_name in tests[:3]:
                terminalreporter.write_line(f"    - {test_name}", yellow=True)
            if len(tests) > 3:
                terminalreporter.write_line(f"    ... 共 {len(tests)} 个测试", yellow=True)
        terminalreporter.write_line("")


@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report):
    """每个测试结果报告"""
    if report.when == "call":
        config = report.config
        if hasattr(config, "_test_summary"):
            summary = config._test_summary

            status_map = {
                "passed": "passed",
                "failed": "failed",
                "skipped": "skipped",
                "error": "error",
            }

            status = status_map.get(report.outcome, "passed")
            summary.collect_result(report.item, status)


def pytest_runtest_setup(item):
    """测试执行前的日志输出"""
    markers = [m.name for m in item.iter_markers()]
    mode = 'REAL_API' if 'real_api' in markers else 'MOCK'

    print(f"\n{'─' * 60}")
    print(f"▶ {item.nodeid}")
    print(f"  markers: {markers or ['default']}")
    print(f"  mode: {mode}")


def pytest_runtest_teardown(item, nextitem):
    """测试结束后的日志"""
    outcome = "✓" if item.rep_call.passed else "✗" if item.rep_call.failed else "○"
    print(f"{outcome} {item.name.split('[')[0]}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """捕获测试结果用于 teardown 日志"""
    outcome = yield
    item.rep_call = outcome.get_result()