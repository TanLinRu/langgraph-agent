"""
Tests for task classifier
"""
import pytest
from src.agent.task_classifier import (
    classify_task,
    should_orchestrate,
    get_routing_decision,
    TaskClassification,
)


class TestTaskClassifier:
    def test_simple_task_query(self):
        result = classify_task("帮我查一下今天天气")
        assert result.complexity == "simple"
        assert result.estimated_steps == 1

    def test_simple_task_translate(self):
        result = classify_task("翻译这段话")
        assert result.complexity == "simple"

    def test_complex_task_develop(self):
        result = classify_task("帮我开发一个用户管理系统")
        assert result.complexity == "complex"
        assert result.estimated_steps >= 2

    def test_complex_task_workflow(self):
        result = classify_task("first do this then do that")
        assert result.complexity == "complex"

    def test_complex_task_multi_step(self):
        result = classify_task("设计一个系统架构，实现用户认证、数据存储和API接口")
        assert result.complexity == "complex"
        assert len(result.keywords_found) >= 1

    def test_simple_question(self):
        result = classify_task("什么是Python?")
        assert result.complexity == "simple"

    def test_should_orchestrate_simple(self):
        result = classify_task("查一下天气")
        assert should_orchestrate(result) is False

    def test_should_orchestrate_complex(self):
        result = classify_task("开发一个网站")
        assert should_orchestrate(result) is True

    def test_get_routing_decision(self):
        result = classify_task("帮我写个API")
        routing = get_routing_decision(result)
        assert "route_to" in routing
        assert "complexity" in routing
        assert "estimated_steps" in routing
        assert "confidence" in routing