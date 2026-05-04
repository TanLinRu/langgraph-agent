import pytest
from unittest.mock import patch


class TestMetrics:

    def _create_agent(self):
        from src.agent.agent import create_agent
        return create_agent(
            model="openai:gpt-4o-mini",
            api_key="test-key",
            base_url="https://api.openai.com/v1",
        )

    def test_estimate_cost_gpt4(self):
        """验证 GPT-4 成本计算"""
        agent = self._create_agent()
        agent.config.model = "openai:gpt-4"

        cost = agent._estimate_cost(prompt_tokens=1000, completion_tokens=500)
        expected = (1000 / 1000 * 0.03) + (500 / 1000 * 0.06)
        assert abs(cost - expected) < 0.0001

    def test_estimate_cost_gpt4o(self):
        """验证 GPT-4o 成本计算"""
        agent = self._create_agent()
        agent.config.model = "openai:gpt-4o"

        cost = agent._estimate_cost(prompt_tokens=1000, completion_tokens=500)
        expected = (1000 / 1000 * 0.005) + (500 / 1000 * 0.015)
        assert abs(cost - expected) < 0.0001

    def test_estimate_cost_gpt4o_mini(self):
        """验证 GPT-4o-mini 成本计算"""
        agent = self._create_agent()
        agent.config.model = "openai:gpt-4o-mini"

        cost = agent._estimate_cost(prompt_tokens=10000, completion_tokens=5000)
        expected = (10000 / 1000 * 0.00015) + (5000 / 1000 * 0.0006)
        assert abs(cost - expected) < 0.00001

    def test_get_metrics_includes_compressions(self):
        """验证指标包含 compressions"""
        agent = self._create_agent()
        agent._metrics["compressions"] = 3

        metrics = agent.get_metrics()
        assert "compressions" in metrics
        assert metrics["compressions"] == 3

    def test_reset_metrics_clears_all(self):
        """验证重置指标清空所有值"""
        agent = self._create_agent()
        agent._metrics["total_requests"] = 10
        agent._metrics["total_tokens"] = 5000
        agent._metrics["compressions"] = 2

        agent.reset_metrics()

        metrics = agent.get_metrics()
        assert metrics["total_requests"] == 0
        assert metrics["total_tokens"] == 0
        assert metrics["compressions"] == 0
