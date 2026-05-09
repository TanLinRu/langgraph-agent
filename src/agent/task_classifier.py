"""
Task Classifier - 任务复杂度分析器

分析用户任务，判断是否需要：
- 简单任务: 直接工具执行
- 复杂任务: 动态编排工作流
"""
import re
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TaskClassification:
    complexity: str  # "simple" | "complex"
    confidence: float  # 0.0 - 1.0
    reason: str
    estimated_steps: int
    keywords_found: list[str]


COMPLEX_KEYWORDS = [
    "开发", "实现", "创建", "构建", "设计", "架构",
    "分析", "优化", "重构", "重构", "迁移",
    "多个", "系统", "集成", "工作流", "流程",
    "debug", "build", "create", "implement", "design",
    "architect", "analyze", "optimize", "refactor",
    "migrate", "integrate", "workflow", "pipeline",
]

COMPOUND_PATTERNS = [
    r"\d+\s+个?\s*[项个]",
    r"先.*再.*然后",
    r"第一步.*第二步",
    r"并且.*并且",
    r"同时.*并且",
    r"\band\b.*\bthen\b",
    r"\bfirst\b.*\bthen\b",
    r"\bstep\d+\b",
]

SIMPLE_PATTERNS = [
    r"^(帮我|请|帮我)?(查|看|找|取|获取)",
    r"^(帮我|请)?(写|生成|创建)\s+\w+\s*(文件|代码|内容)",
    r"^(翻译|解释|总结|描述)",
    r"^(计算|算一下|帮我算)",
    r"\bwhat\b.*\btime\b",
    r"\bhow\b.*\bdoing\b",
    r"\bshow\b",
    r"\bget\b",
]


def classify_task(task: str, llm=None) -> TaskClassification:
    """
    分类任务复杂度

    Returns:
        TaskClassification with complexity, confidence, reason
    """
    task = task.strip()
    task_lower = task.lower()

    keywords_found = []
    complexity_score = 0

    for kw in COMPLEX_KEYWORDS:
        if kw.lower() in task_lower:
            keywords_found.append(kw)
            complexity_score += 3

    for pattern in COMPOUND_PATTERNS:
        if re.search(pattern, task_lower):
            complexity_score += 3

    for pattern in SIMPLE_PATTERNS:
        if re.search(pattern, task_lower):
            complexity_score -= 2

    task_length = len(task)
    if task_length > 200:
        complexity_score += 2
    elif task_length > 500:
        complexity_score += 4

    if "?" in task or "？" in task:
        complexity_score -= 1

    if complexity_score >= 3:
        estimated = min(6, 2 + complexity_score // 2)
        return TaskClassification(
            complexity="complex",
            confidence=min(0.95, 0.5 + complexity_score * 0.1),
            reason=f"发现 {len(keywords_found)} 个复杂关键词，模式匹配得分 {complexity_score}",
            estimated_steps=estimated,
            keywords_found=keywords_found,
        )
    else:
        return TaskClassification(
            complexity="simple",
            confidence=min(0.9, 0.6 - complexity_score * 0.1),
            reason=f"简单任务，复杂度得分 {complexity_score}",
            estimated_steps=1,
            keywords_found=keywords_found,
        )


def should_orchestrate(classification: TaskClassification) -> bool:
    """判断是否需要使用编排器"""
    return classification.complexity == "complex"


def get_routing_decision(classification: TaskClassification) -> dict:
    """获取路由决策"""
    return {
        "route_to": "orchestrator" if should_orchestrate(classification) else "direct",
        "complexity": classification.complexity,
        "estimated_steps": classification.estimated_steps,
        "confidence": classification.confidence,
        "reason": classification.reason,
    }