"""
Agent 注册表管理

负责 Agent 定义、配置、关系图的存储和查询
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Agent 注册表"""

    def __init__(self, memory_dir: str = "./memory"):
        self.memory_dir = Path(memory_dir)
        self.agents_file = self.memory_dir / "agents.json"
        self.graphs_file = self.memory_dir / "agent_graphs.json"
        self._ensure_dir()
        self._agents_cache = None
        self._graphs_cache = None

    def _ensure_dir(self):
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _load_agents(self) -> list:
        """加载所有 Agent 定义"""
        if self._agents_cache is not None:
            return self._agents_cache
        
        if self.agents_file.exists():
            with open(self.agents_file, "r", encoding="utf-8") as f:
                self._agents_cache = json.load(f)
        else:
            self._agents_cache = self._init_builtin_agents()
            self._save_agents()
        return self._agents_cache

    def _save_agents(self):
        """保存 Agent 定义"""
        with open(self.agents_file, "w", encoding="utf-8") as f:
            json.dump(self._agents_cache, f, indent=2, ensure_ascii=False)

    def _init_builtin_agents(self) -> list:
        """初始化内置 Agent（从现有 skills 转换）"""
        from .skills import SKILLS_REGISTRY
        
        builtin_agents = []
        
        # 添加 OpenCode Agent (通过 opencode run 调用)
        opencode_agent = {
            "id": "opencode-agent",
            "name": "OpenCode",
            "description": "通用代码开发 Agent，通过 opencode run 调度外部 OpenCode",
            "llm_model": "openai:gpt-4",
            "system_prompt": "你是专业的代码开发助手。擅长代码编写、调试、重构和技术问题解答。",
            "tools": [],
            "execution_mode": "acp",  # 复用 acp 模式标识
            "timeout": 180,
            "skill": None,
            "is_builtin": True,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        builtin_agents.append(opencode_agent)
        
        # 添加其他内置 Agent（从 skills 转换）
        for skill_name, skill_info in SKILLS_REGISTRY.items():
            agent = {
                "id": f"builtin-{skill_name}",
                "name": skill_info["description"],
                "description": skill_info["description"],
                "llm_model": "openai:gpt-4",
                "system_prompt": skill_info["full_content"],
                "tools": [],  # 默认空，运行时按需分配
                "execution_mode": "sync",
                "timeout": 60,
                "is_builtin": True,
                "skill_source": skill_name,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            builtin_agents.append(agent)
        
        logger.info(f"初始化 {len(builtin_agents)} 个内置 Agent")
        return builtin_agents

    def list_agents(self) -> list:
        """列出所有 Agent"""
        agents = self._load_agents()
        # 返回时隐藏完整 prompt
        result = []
        for a in agents:
            result.append({
                "id": a["id"],
                "name": a["name"],
                "description": a["description"],
                "llm_model": a["llm_model"],
                "tools": a.get("tools", []),
                "execution_mode": a.get("execution_mode", "sync"),
                "timeout": a.get("timeout", 60),
                "is_builtin": a.get("is_builtin", False),
                "created_at": a.get("created_at"),
                "updated_at": a.get("updated_at"),
            })
        return result

    def get_agent(self, agent_id: str) -> Optional[dict]:
        """获取单个 Agent 详情"""
        agents = self._load_agents()
        for a in agents:
            if a["id"] == agent_id:
                return a
        return None

    def create_agent(self, agent_data: dict) -> dict:
        """创建新 Agent"""
        agents = self._load_agents()
        
        agent_id = agent_data.get("id") or f"agent-{len(agents)+1}-{int(datetime.now().timestamp())}"
        
        new_agent = {
            "id": agent_id,
            "name": agent_data.get("name", "未命名 Agent"),
            "description": agent_data.get("description", ""),
            "llm_model": agent_data.get("llm_model", "openai:gpt-4"),
            "system_prompt": agent_data.get("system_prompt", ""),
            "tools": agent_data.get("tools", []),
            "execution_mode": agent_data.get("execution_mode", "sync"),
            "timeout": agent_data.get("timeout", 60),
            "is_builtin": False,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        agents.append(new_agent)
        self._agents_cache = agents
        self._save_agents()
        
        logger.info(f"创建 Agent: {agent_id}")
        return new_agent

    def update_agent(self, agent_id: str, agent_data: dict) -> Optional[dict]:
        """更新 Agent"""
        agents = self._load_agents()
        
        for i, a in enumerate(agents):
            if a["id"] == agent_id:
                # 不允许修改内置 Agent
                if a.get("is_builtin"):
                    logger.warning(f"尝试修改内置 Agent: {agent_id}")
                    return None
                
                a.update(agent_data)
                a["updated_at"] = datetime.now().isoformat()
                agents[i] = a
                self._agents_cache = agents
                self._save_agents()
                
                logger.info(f"更新 Agent: {agent_id}")
                return a
        
        return None

    def delete_agent(self, agent_id: str) -> bool:
        """删除 Agent"""
        agents = self._load_agents()
        
        for i, a in enumerate(agents):
            if a["id"] == agent_id:
                if a.get("is_builtin"):
                    logger.warning(f"尝试删除内置 Agent: {agent_id}")
                    return False
                
                del agents[i]
                self._agents_cache = agents
                self._save_agents()
                
                logger.info(f"删除 Agent: {agent_id}")
                return True
        
        return False

    # === Agent Graph 相关方法 ===

    def _load_graphs(self) -> list:
        """加载所有 Agent Graph"""
        if self._graphs_cache is not None:
            return self._graphs_cache
        
        if self.graphs_file.exists():
            with open(self.graphs_file, "r", encoding="utf-8") as f:
                self._graphs_cache = json.load(f)
        else:
            self._graphs_cache = []
            self._save_graphs()
        return self._graphs_cache

    def _save_graphs(self):
        """保存 Agent Graph"""
        with open(self.graphs_file, "w", encoding="utf-8") as f:
            json.dump(self._graphs_cache, f, indent=2, ensure_ascii=False)

    def list_graphs(self) -> list:
        """列出所有 Graph"""
        return self._load_graphs()

    def get_graph(self, graph_id: str) -> Optional[dict]:
        """获取 Graph 详情"""
        graphs = self._load_graphs()
        for g in graphs:
            if g["id"] == graph_id:
                return g
        return None

    def create_graph(self, graph_data: dict) -> dict:
        """创建 Graph"""
        graphs = self._load_graphs()
        
        graph_id = graph_data.get("id") or f"graph-{len(graphs)+1}-{int(datetime.now().timestamp())}"
        
        new_graph = {
            "id": graph_id,
            "name": graph_data.get("name", "未命名 Graph"),
            "description": graph_data.get("description", ""),
            "nodes": graph_data.get("nodes", []),
            "edges": graph_data.get("edges", []),
            "parallel_groups": graph_data.get("parallel_groups", []),
            "config": graph_data.get("config", {}),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        graphs.append(new_graph)
        self._graphs_cache = graphs
        self._save_graphs()
        
        logger.info(f"创建 Graph: {graph_id}")
        return new_graph

    def update_graph(self, graph_id: str, graph_data: dict) -> Optional[dict]:
        """更新 Graph"""
        graphs = self._load_graphs()
        
        for i, g in enumerate(graphs):
            if g["id"] == graph_id:
                g.update(graph_data)
                g["updated_at"] = datetime.now().isoformat()
                graphs[i] = g
                self._graphs_cache = graphs
                self._save_graphs()
                
                logger.info(f"更新 Graph: {graph_id}")
                return g
        
        return None

    def delete_graph(self, graph_id: str) -> bool:
        """删除 Graph"""
        graphs = self._load_graphs()
        
        graphs = [g for g in graphs if g["id"] != graph_id]
        
        if len(graphs) != len(self._graphs_cache):
            self._graphs_cache = graphs
            self._save_graphs()
            logger.info(f"删除 Graph: {graph_id}")
            return True
        
        return False


# 全局实例
_registry: Optional[AgentRegistry] = None


def get_registry(memory_dir: str = "./memory") -> AgentRegistry:
    """获取全局注册表实例"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry(memory_dir)
    return _registry