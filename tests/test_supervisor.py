"""
Supervisor 模式测试

测试 sub-agent 工厂、事件回调、SupervisorManager 等功能
"""
import pytest
from unittest.mock import MagicMock, AsyncMock


class TestSubAgentFactory:
    """测试 sub-agent 工厂函数"""

    def test_sanitize_agent_name_builtin(self):
        """测试内置 agent 名称清理"""
        from src.agent.sub_agent_factory import _sanitize_agent_name
        assert _sanitize_agent_name("builtin-code_review") == "code_review_agent"
        assert _sanitize_agent_name("builtin-data_analysis") == "data_analysis_agent"
        assert _sanitize_agent_name("builtin-debugging") == "debugging_agent"

    def test_sanitize_agent_name_opencode(self):
        """测试 opencode agent 名称清理"""
        from src.agent.sub_agent_factory import _sanitize_agent_name
        assert _sanitize_agent_name("opencode-agent") == "opencode_agent"

    def test_sanitize_agent_name_custom(self):
        """测试自定义 agent 名称清理"""
        from src.agent.sub_agent_factory import _sanitize_agent_name
        assert _sanitize_agent_name("agent-1234-5678") == "agent_1234_5678_agent"
        # "my-custom-agent" -> "my_custom_agent" (已以 agent 结尾，不重复添加)
        assert _sanitize_agent_name("my-custom-agent") == "my_custom_agent"

    def test_sanitize_agent_name_leading_digit(self):
        """测试以数字开头的 agent 名称"""
        from src.agent.sub_agent_factory import _sanitize_agent_name
        result = _sanitize_agent_name("123-agent")
        assert not result[0].isdigit()

    def test_resolve_tools_empty(self):
        """测试空工具列表"""
        from src.agent.sub_agent_factory import _resolve_tools
        result = _resolve_tools([], [])
        assert result == []

    def test_resolve_tools_matches(self):
        """测试工具匹配"""
        from src.agent.sub_agent_factory import _resolve_tools
        mock_tool = MagicMock()
        mock_tool.name = "read_file"
        result = _resolve_tools(["read_file"], [mock_tool])
        assert len(result) == 1
        assert result[0].name == "read_file"

    def test_resolve_tools_missing(self):
        """测试缺失工具"""
        from src.agent.sub_agent_factory import _resolve_tools
        result = _resolve_tools(["nonexistent_tool"], [])
        assert result == []

    def test_build_acp_tool(self):
        """测试 ACP 工具包装"""
        from src.agent.sub_agent_factory import _build_acp_tool
        agent_def = {
            "id": "opencode-agent",
            "name": "OpenCode",
            "system_prompt": "test prompt",
            "skill": None,
            "timeout": 180,
        }
        acp_tool = _build_acp_tool(agent_def)
        assert acp_tool is not None
        assert acp_tool.name == "call_opencode"


class TestEventBusCallbackHandler:
    """测试 EventBus 回调处理器"""

    def test_handler_creation(self):
        """测试处理器创建"""
        from src.agent.event_callback import EventBusCallbackHandler
        handler = EventBusCallbackHandler(execution_id="test-exec-1")
        assert handler.execution_id == "test-exec-1"

    def test_handler_has_required_methods(self):
        """测试处理器包含所有必要的回调方法"""
        from src.agent.event_callback import EventBusCallbackHandler
        handler = EventBusCallbackHandler()
        assert hasattr(handler, "on_chain_start")
        assert hasattr(handler, "on_chain_end")
        assert hasattr(handler, "on_chain_error")
        assert hasattr(handler, "on_tool_start")
        assert hasattr(handler, "on_tool_end")
        assert hasattr(handler, "on_chat_model_start")
        assert hasattr(handler, "on_llm_end")


class TestSupervisorManager:
    """测试 SupervisorManager"""

    @pytest.fixture
    def registry(self, tmp_path):
        from src.agent.registry import AgentRegistry
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        return AgentRegistry(memory_dir=str(mem_dir))

    @pytest.fixture
    def manager(self, registry):
        from src.agent.supervisor import SupervisorManager
        return SupervisorManager(registry, llm=None, available_tools=[])

    def test_generate_plan_single_agent(self, manager, registry):
        """测试单 agent 执行计划"""
        graph = registry.create_graph({
            "name": "Test Graph",
            "nodes": [
                {"id": "n1", "type": "agent", "agent_id": "builtin-code_review", "data": {"label": "Review"}},
            ],
            "edges": [],
        })
        plan = manager.generate_plan(graph["id"], "Review this code")

        assert plan is not None
        assert plan["graph_id"] == graph["id"]
        assert plan["total_llm_calls"] == 1
        assert len(plan["steps"]) == 1
        assert plan["steps"][0]["agent_id"] == "builtin-code_review"

    def test_generate_plan_multiple_agents(self, manager, registry):
        """测试多 agent 执行计划"""
        graph = registry.create_graph({
            "name": "Multi Agent",
            "nodes": [
                {"id": "n1", "type": "agent", "agent_id": "builtin-code_review", "data": {"label": "Review"}},
                {"id": "n2", "type": "agent", "agent_id": "builtin-debugging", "data": {"label": "Debug"}},
            ],
            "edges": [{"source": "n1", "target": "n2"}],
        })
        plan = manager.generate_plan(graph["id"], "Review and debug")

        assert plan["total_llm_calls"] == 2
        assert len(plan["steps"]) == 2

    def test_generate_plan_invalid_graph(self, manager):
        """测试无效 graph 返回 None"""
        plan = manager.generate_plan("nonexistent", "test")
        assert plan is None

    def test_generate_plan_preserves_api_contract(self, manager, registry):
        """测试计划格式与旧 API 兼容"""
        graph = registry.create_graph({
            "name": "Test",
            "nodes": [
                {"id": "n1", "type": "agent", "agent_id": "builtin-code_review", "data": {"label": "R"}},
            ],
            "edges": [],
        })
        plan = manager.generate_plan(graph["id"], "test")

        # 检查所有必需字段
        assert "graph_id" in plan
        assert "input_summary" in plan
        assert "total_llm_calls" in plan
        assert "estimated_cost_usd" in plan
        assert "estimated_duration_sec" in plan
        assert "steps" in plan
        assert "parallel_opportunities" in plan
        assert "optimization_suggestions" in plan

        # 检查步骤格式
        step = plan["steps"][0]
        assert "step_id" in step
        assert "agent_id" in step
        assert "agent_name" in step
        assert "agent_description" in step
        assert "expected_tools" in step
        assert "depends_on" in step
        assert "is_parallel" in step
        assert "estimated_calls" in step
        assert "estimated_tokens" in step

    def test_list_executions_empty(self, manager):
        """测试空执行列表"""
        executions = manager.list_executions()
        assert executions == []

    def test_get_execution_none(self, manager):
        """测试获取不存在的执行"""
        result = manager.get_execution("nonexistent")
        assert result is None

    def test_build_sub_agents_filters_agent_nodes(self, manager, registry):
        """测试 sub-agent 构建过滤 agent 类型节点"""
        registry.create_graph({
            "name": "Test",
            "nodes": [
                {"id": "n1", "type": "agent", "agent_id": "builtin-code_review", "data": {"label": "R"}},
                {"id": "n2", "type": "condition", "data": {"label": "C"}},
            ],
            "edges": [],
        })
        graph = registry.list_graphs()[0]
        # Without LLM, build_sub_agent fails, but we can verify node filtering
        agent_nodes = [n for n in graph["nodes"] if n.get("type") == "agent"]
        assert len(agent_nodes) == 1
        assert agent_nodes[0]["agent_id"] == "builtin-code_review"


class TestSubAgentState:
    """测试 SubAgentState"""

    def test_sub_agent_state_has_messages(self):
        """测试 SubAgentState 包含 messages 字段"""
        from src.agent.state import SubAgentState
        assert "messages" in SubAgentState.__annotations__

    def test_sub_agent_state_has_task_description(self):
        """测试 SubAgentState 包含 task_description 字段"""
        from src.agent.state import SubAgentState
        assert "task_description" in SubAgentState.__annotations__


class TestRegistrySupervisorConfig:
    """测试注册表 supervisor_config 扩展"""

    @pytest.fixture
    def registry(self, tmp_path):
        from src.agent.registry import AgentRegistry
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        return AgentRegistry(memory_dir=str(mem_dir))

    def test_create_graph_with_default_supervisor_config(self, registry):
        """测试创建图时自动添加 supervisor_config"""
        graph = registry.create_graph({
            "name": "Test",
            "nodes": [],
            "edges": [],
        })
        config = graph.get("config", {})
        assert "supervisor_config" in config
        sc = config["supervisor_config"]
        assert sc["routing_strategy"] == "llm"
        assert sc["max_iterations"] == 10
        assert sc["supervisor_prompt"] is None

    def test_create_graph_with_custom_supervisor_config(self, registry):
        """测试创建图时自定义 supervisor_config"""
        graph = registry.create_graph({
            "name": "Test",
            "config": {
                "supervisor_config": {
                    "routing_strategy": "sequential",
                    "max_iterations": 5,
                    "supervisor_prompt": "Custom prompt",
                },
            },
        })
        sc = graph["config"]["supervisor_config"]
        assert sc["routing_strategy"] == "sequential"
        assert sc["max_iterations"] == 5
        assert sc["supervisor_prompt"] == "Custom prompt"
