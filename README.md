# LangGraph Agent

> 生产级代码开发与数据处理 Agent，集成 OpenCode 作为外部执行引擎

## 快速开始

```bash
# 安装依赖
pip install -e .

# 复制配置
cp .env.example .env
# 编辑 .env 填入 API Key

# 运行
python -m src.agent.main --input "写一个快速排序"

# 交互模式
python -m src.agent.main --interactive

# 启动后端服务
python server.py

# 前端开发（另开终端）
cd ui && npm install && npm run dev
```

## 项目结构

```
langgraph-agent/
├── src/agent/              # 核心代码
│   ├── context/            # 上下文管理
│   │   ├── long_term.py    # SQLite + ChromaDB 长期记忆
│   │   ├── compression.py # LLM 摘要压缩
│   │   ├── initialization.py # 重启恢复
│   │   └── archive.py     # 归档
│   ├── prompts/           # 系统提示
│   ├── skills/            # 技能系统
│   ├── tools/             # 工具集
│   ├── agent.py           # 主入口
│   ├── orchestrator.py   # 多 Agent 编排
│   ├── registry.py       # Agent 注册
│   ├── opencode_client.py # OpenCode CLI 客户端
│   └── acp_stdio_client.py # ACP Stdio 客户端（备用）
│
├── ui/                    # 前端 Vue 项目
│
├── memory/                # 会话存储
│
├── tests/                 # pytest 测试
│
├── docs/                  # 文档
│
└── server.py             # 后端 HTTP API
```

## OpenCode 集成

通过 execution_mode: acp 属性，可以将 OpenCode 作为外部 Agent 调用：

```python
opencode_agent = {
    "id": "opencode-agent",
    "name": "OpenCode",
    "execution_mode": "acp",
    "timeout": 180,
    "skill": None,
}
```

## 特性

- OpenCode 集成: 通过 CLI/ACP 调度外部 OpenCode 执行任务
- 上下文压缩: 70% 阈值触发 LLM 摘要
- 长期记忆: MEMORY.md + ChromaDB 向量
- 会话存储: SQLite + JSONL
- 自动归档: 7 天自动归档

## 测试

```bash
pytest tests/
```