# LangChain、LangGraph 与 Deep Agents 完整指南

> 构建生产级代码开发与数据处理 Agent 的实战手册

LangChain 生态系统包含三个层次的工具：**框架 (Framework)** 提供抽象，**运行时 (Runtime)** 提供持久执行能力，**脚手架 (Harness)** 提供开箱即用的 Agent 能力。理解三者关系是构建生产级系统的基础。

---

## 1. 技术定位与关系

### 1.1 三个层次的职责

| 层次 | 产品 | 核心价值 | 典型场景 |
|------|------|----------|----------|
| **Framework** | LangChain | 快速入门、标准化抽象、模型集成 | 简单 Agent、RAG 应用 |
| **Runtime** | LangGraph | 持久执行、流式输出、状态管理 | 复杂工作流、长时运行 Agent |
| **Harness** | Deep Agents | 预置工具、子 Agent、规划能力 | 自主代码开发、数据处理 Pipeline |

### 1.2 技术栈叠加关系

```
┌─────────────────────────────────────────┐
│           Deep Agents SDK                │  ← 脚手架层：开箱即用
│  ┌─────────────────────────────────────┐ │
│  │     LangChain (Framework)          │  │  ← 框架层：抽象接口
│  │  ┌───────────────────────────────┐  │ │
│  │  │     LangGraph (Runtime)       │  │ │  ← 运行时层：状态+执行
│  │  │  ┌─────────────────────────┐  │  │ │
│  │  │  │  Models + Tools + LLM   │  │  │ │
│  │  │  └─────────────────────────┘  │  │ │
│  │  └───────────────────────────────┘  │ │
│  └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

### 1.3 选型路径

```
简单任务 (单轮问答)
    │
    ▼
LangChain → 快速构建，标准抽象
    │
    ▼ (复杂化)
复杂工作流 + 状态持久化
    │
    ▼
LangGraph → 图结构编排、断点恢复
    │
    ▼ (进一步复杂化)
自主 Agent + 长期运行
    │
    ▼
Deep Agents → 预置工具、规划能力、子 Agent
```

---

## 2. LangChain 入门

### 2.1 核心概念

LangChain 提供四个基础抽象：

- **Model**：LLM 接口（OpenAI、Anthropic、Ollama 等）
- **Prompt**：提示模板（ChatPromptTemplate）
- **Output Parser**：输出解析（JSON、XML、Structued）
- **Tool**：工具（函数 + 描述）

### 2.2 LCEL 表达式语言

LCEL (LangChain Expression Language) 是链式调用的核心语法：

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

prompt = ChatPromptTemplate.from_template("用 {language} 写一个 {task}")
model = ChatOpenAI(model="gpt-4")
parser = StrOutputParser()

# 链式调用
chain = prompt | model | parser

result = chain.invoke({
    "language": "Python",
    "task": "快速排序算法"
})
```

### 2.3 简单 Agent 构建

使用 LangChain 的 `create_agent` 工厂函数：

```python
from langchain.agents import create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain import hub

# 获取预置提示
prompt = hub.pull("hwchase17/openai-functions-agent")

# 创建模型
llm = ChatOpenAI(model="gpt-4", temperature=0)

# 定义工具
def calculate(expression: str) -> str:
    """执行数学计算"""
    return str(eval(expression))

# 创建 Agent
agent = create_openai_functions_agent(llm, [calculate], prompt)

# 执行
from langchain.agents import AgentExecutor
executor = AgentExecutor(agent=agent, tools=[calculate], verbose=True)

result = executor.invoke({"input": "计算 (15 + 25) * 3 的结果"})
```

### 2.4 生产应用要点

1. **错误处理**：LCEL 支持 `with_fallbacks` 链式错误处理
2. **流式输出**：使用 `stream` 方法而非 `invoke`
3. **回调系统**：LangSmith 集成用于追踪

```python
from langchain.callbacks.langsmith import LangSmithCallbackHandler

handler = LangSmithCallbackHandler(
    project_name="my-agent",
    metadata={"user_id": "123"}
)

chain = prompt | model | parser
result = chain.invoke({"input": "..."}, config={"callbacks": [handler]})
```

---

## 3. LangGraph 深入

### 3.1 为什么需要 LangGraph

LangChain 的 Agent 是简单的循环：LLM → 工具调用 → 结果 → LLM。这个循环在长时运行时会遇到问题：

- **状态丢失**：失败后无法从断点恢复
- **无流式输出**：必须等待完整结果
- **无法人机交互**：无法在关键步骤插入人工审核

LangGraph 通过图结构 + 状态持久化解决这些问题。

### 3.2 StateGraph 核心概念

```python
from typing import TypedDict
from langgraph.graph import StateGraph, END

# 定义状态 schema
class AgentState(TypedDict):
    messages: list
    next_action: str | None
    task_status: str  # pending, in_progress, completed, failed
```

### 3.3 构建一个代码开发 Agent

以下是完整的工作流编排示例：

```python
from typing import TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# ============================================
# 步骤 1: 定义状态
# ============================================
class CodeDevState(TypedDict):
    messages: Annotated[list, operator.add]
    task_description: str
    plan: list | None
    current_step: str
    code_output: str | None
    error: str | None

# ============================================
# 步骤 2: 定义节点函数
# ============================================
llm = ChatOpenAI(model="gpt-4", temperature=0)

def analyze_task(state: CodeDevState) -> CodeDevState:
    """分析任务，生成执行计划"""
    task = state["task_description"]
    
    response = llm.invoke([
        SystemMessage(content="你是一个代码开发规划助手。将任务分解为步骤。"),
        HumanMessage(content=f"为以下任务生成执行计划：{task}")
    ])
    
    plan = response.content.split("\n")
    return {"plan": plan, "current_step": "analyzing"}

def execute_code(state: CodeDevState) -> CodeDevState:
    """执行代码（模拟）"""
    plan = state["plan"]
    current = state["current_step"]
    
    # 模拟代码执行
    code_result = f"Executed step: {current}"
    return {"code_output": code_result, "current_step": "executing"}

def verify_result(state: CodeDevState) -> CodeDevState:
    """验证执行结果"""
    code = state.get("code_output", "")
    
    # LLM 判断是否成功
    response = llm.invoke([
        HumanMessage(content=f"判断以下代码执行是否成功：{code}")
    ])
    
    if "成功" in response.content or "成功" in response.content:
        return {"task_status": "completed"}
    else:
        return {"task_status": "failed", "error": "Verification failed"}

# ============================================
# 步骤 3: 构建图
# ============================================
workflow = StateGraph(CodeDevState)

# 添加节点
workflow.add_node("analyze", analyze_task)
workflow.add_node("execute", execute_code)
workflow.add_node("verify", verify_result)

# 设置入口
workflow.set_entry_point("analyze")

# 添加边
workflow.add_edge("analyze", "execute")
workflow.add_edge("execute", "verify")

# 条件边：验证失败则重试
def should_retry(state: CodeDevState) -> str:
    if state.get("task_status") == "failed":
        return "execute"  # 回到执行
    return END

workflow.add_conditional_edges("verify", should_retry)

# ============================================
# 步骤 4: 编译图
# ============================================
app = workflow.compile()

# ============================================
# 步骤 5: 执行
# ============================================
result = app.invoke({
    "messages": [],
    "task_description": "实现一个 Python 函数来计算斐波那契数列",
    "plan": None,
    "current_step": "",
    "code_output": None,
    "error": None
})

print(result)
```

### 3.4 Checkpoint 持久化

LangGraph 的核心能力是断点恢复：

```python
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.memory import MemorySaver

# 内存持久化（开发环境）
checkpointer = MemorySaver()

# PostgreSQL 持久化（生产环境）
checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@localhost:5432/langgraph"
)

# 编译时注入 checkpointer
app = workflow.compile(checkpointer=checkpointer)

# 执行时指定 thread_id
config = {"configurable": {"thread_id": "session-123"}}
result = app.invoke(input_state, config)

# 恢复会话
result2 = app.invoke({"messages": []}, config)
```

### 3.5 Human-in-the-loop

通过 `interrupt` 实现人工审核：

```python
from langgraph.types import interrupt

def human_review(state: CodeDevState) -> CodeDevState:
    # 中断执行，等待人工审核
    review_result = interrupt({
        "question": "是否批准执行此代码？",
        "code": state["code_output"]
    })
    
    if review_result["approved"]:
        return {"current_step": "approved"}
    else:
        return {"current_step": "rejected", "error": "Rejected by human"}

# 工作流中添加审核节点
workflow.add_node("human_review", human_review)
workflow.add_edge("execute", "human_review")
```

### 3.6 Streaming 输出

```python
# 流式输出所有节点
for event in app.stream(input_state, stream_mode="values"):
    print(event)

# 或只流式输出最终结果
for token in app.stream(input_state, stream_mode="accumulate"):
    print(token, end="")
```

---

## 4. Deep Agents 实战

### 4.1 为什么使用 Deep Agents

对于代码开发和数据处理场景，Deep Agents 提供开箱即用的能力：

- 内置文件操作工具
- 任务规划与 todo 列表
- 自动上下文压缩
- 子 Agent 隔离

### 4.2 创建 Deep Agent

```python
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

# 方式 1：简单创建
agent = create_deep_agent(
    model="openai:gpt-4",
    tools=[],  # 可选：自定义工具
    system_prompt="你是一个专业的代码开发助手"
)

# 执行
result = agent.invoke({
    "messages": [{"role": "user", "content": "帮我写一个快速排序"}]
})
```

### 4.3 完整代码开发 Agent 示例

```python
from deepagents import create_deep_agent
from deepagents.core import Tool
from langchain_openai import ChatOpenAI

# ============================================
# 自定义工具：代码执行
# ============================================
class CodeExecutor(Tool):
    name = "execute_code"
    description = """执行 Python 代码并返回结果。
    
    Use when: 你需要运行代码来验证、计算或生成结果时
    Don't use when: 只是讨论代码而不需要实际执行"""
    
    def run(self, code: str) -> str:
        """执行代码并返回输出"""
        import subprocess
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False
        ) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            result = subprocess.run(
                ['python', temp_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            output = result.stdout + result.stderr
            return output or "代码执行完成，无输出"
        except Exception as e:
            return f"执行错误: {str(e)}"
        finally:
            os.unlink(temp_path)

# ============================================
# 自定义工具：文件读写
# ============================================
class FileOperator(Tool):
    name = "file_operator"
    description = """读取或写入文件。
    
    Use when: 需要读取代码文件或保存结果时
    Don't use when: 只需要内存中的数据"""
    
    def run(self, operation: str, path: str, content: str = "") -> str:
        if operation == "read":
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        elif operation == "write":
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"已写入 {path}"
        else:
            return "无效操作"

# ============================================
# 创建 Agent
# ============================================
agent = create_deep_agent(
    model="openai:gpt-4",
    tools=[CodeExecutor(), FileOperator()],
    system_prompt="""你是一个专业的 Python 开发助手。

工作流程：
1. 理解需求，编写代码
2. 执行验证，确保正确
3. 保存结果到文件

重要规则：
- 复杂代码先写测试
- 执行前检查语法
- 错误要明确指出原因"""
)

# ============================================
# 执行开发任务
# ============================================
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": """实现一个数据处理 Pipeline：
1. 读取 CSV 文件 data.csv
2. 清洗缺失值
3. 按日期分组统计
4. 输出结果到 result.csv"""
    }]
})
```

### 4.4 数据处理 Agent 示例

```python
from deepagents import create_deep_agent
from deepagents.core import Tool
import pandas as pd
from langchain_openai import ChatOpenAI

# ============================================
# 数据处理工具集
# ============================================
class DataProcessor(Tool):
    name = "process_data"
    description = """处理和分析结构化数据（CSV、JSON）。
    
    Use when: 需要清洗、转换、聚合数据时
    Don't use when: 只是读取文件查看内容"""
    
    def run(self, operation: str, file_path: str, params: dict = None) -> str:
        params = params or {}
        df = pd.read_csv(file_path)
        
        if operation == "head":
            return df.head(params.get("n", 5)).to_string()
        
        elif operation == "describe":
            return df.describe().to_string()
        
        elif operation == "dropna":
            df_clean = df.dropna()
            df_clean.to_csv(file_path, index=False)
            return f"已删除 {len(df) - len(df_clean)} 行缺失数据"
        
        elif operation == "groupby":
            col = params.get("group_col")
            agg_col = params.get("agg_col")
            result = df.groupby(col)[agg_col].agg(['sum', 'mean', 'count'])
            return result.to_string()
        
        elif operation == "filter":
            col = params.get("column")
            val = params.get("value")
            filtered = df[df[col] == val]
            return f"筛选出 {len(filtered)} 行\n{filtered.head(10).to_string()}"
        
        return "未知操作"

class DataVisualizer(Tool):
    name = "visualize_data"
    description = """生成数据可视化。
    
    Use when: 需要图表来理解数据分布或趋势时
    Don't use when: 只需要数值分析结果"""
    
    def run(self, chart_type: str, file_path: str, params: dict = None) -> str:
        import matplotlib.pyplot as plt
        params = params or {}
        df = pd.read_csv(file_path)
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        if chart_type == "bar":
            x = params.get("x")
            y = params.get("y")
            df.plot(kind='bar', x=x, y=y, ax=ax)
        
        elif chart_type == "line":
            x = params.get("x")
            y = params.get("y")
            df.plot(kind='line', x=x, y=y, ax=ax)
        
        elif chart_type == "hist":
            col = params.get("column")
            df[col].hist(ax=ax)
        
        output_path = params.get("output", "chart.png")
        plt.savefig(output_path)
        plt.close()
        return f"图表已保存到 {output_path}"

# ============================================
# 创建数据处理 Agent
# ============================================
agent = create_deep_agent(
    model="openai:gpt-4",
    tools=[DataProcessor(), DataVisualizer()],
    system_prompt="""你是数据处理专家。

能力：
- 数据清洗与转换
- 统计分析
- 可视化生成

工作流程：
1. 先了解数据结构（describe, head）
2. 进行必要的数据清洗
3. 执行分析或可视化
4. 解释结果含义"""
)

# ============================================
# 执行数据处理任务
# ============================================
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": """分析 sales_data.csv：
1. 查看数据基本情况
2. 按 product_category 分组统计销售额
3. 生成趋势图保存为 sales_chart.png"""
    }]
})
```

### 4.5 Subagent 委派

Deep Agents 支持委派子任务：

```python
# 在 Agent 提示中添加子任务指令
system_prompt = """你是主 Agent，负责协调子任务。

当需要深入分析时，可以使用 task 工具委派给子 Agent。
子 Agent 会获得独立的上下文，完成后返回结果。"""

# 子 Agent 配置
subagent = create_deep_agent(
    model="openai:gpt-4",
    tools=[CodeExecutor()],
    system_prompt="你是代码审查专家，关注性能和安全性"
)
```

### 4.6 Skills 系统

Skills 提供可复用的技能包：

```python
from deepagents.skills import Skill

# 定义一个代码审查 Skill
review_skill = Skill(
    name="code_review",
    description="审查代码质量和安全性",
    instructions="""执行以下审查：
1. 代码风格检查
2. 潜在 bug 分析
3. 性能问题识别
4. 安全漏洞扫描

每个问题要给出具体行号和修复建议。""",
    tools=[CodeExecutor()]  # 技能可用的工具
)

# 添加到 Agent
agent = create_deep_agent(
    model="openai:gpt-4",
    skills=[review_skill]
)
```

---

## 5. 生产级架构

### 5.1 技术选型路径

```
开发阶段                    生产阶段
─────────────────────────►─────────────────────────
 │                         │
 ▼                         ▼
LangChain + MemorySaver    LangGraph + Postgres
 │                         │
 ▼                         ▼
开发验证                    Deep Agents
 │                         │
 ▼                         ▼
单一 Agent                  多 Agent 编排
 │                         │
 ▼                         ▼
LangSmith 本地              LangSmith Cloud
```

### 5.2 LangSmith 可观测性集成

```python
from langchain.callbacks.langsmith import LangSmithCallbackHandler

# 环境变量方式
import os
os.environ["LANGSMITH_PROJECT"] = "my-agent"
os.environ["LANGSMITH_TRACING"] = "true"

# 或显式配置
handler = LangSmithCallbackHandler(
    project_name="production-agent",
    metadata={
        "environment": "production",
        "agent_version": "1.0.0"
    }
)

# 在执行链中注入
result = chain.invoke(
    input_data,
    config={"callbacks": [handler]}
)
```

### 5.3 评测体系构建

```python
from langsmith import Client
from langsmith.evaluation import evaluate

client = Client()

# 定义评测数据集
dataset = client.create_dataset(
    name="code-generation-eval",
    description="代码生成能力评测"
)

# 添加评测用例
client.create_examples(
    dataset_id=dataset.id,
    inputs=[
        {"task": "写一个快速排序"},
        {"task": "实现二分查找"},
        {"task": "创建数据类"},
    ],
    outputs=[
        {"expected": "包含完整代码和测试"},
    ]
)

# 定义评测器
def code_quality_evaluator(prediction, example):
    code = prediction["output"]
    return {
        "score": 1 if "def" in code and "return" in code else 0,
        "reasoning": "检查代码是否包含函数定义和返回语句"
    }

# 运行评测
results = evaluate(
    agent_executor.invoke,
    data="code-generation-eval",
    evaluators=[code_quality_evaluator],
    experiment_name="gpt-4-baseline"
)
```

### 5.4 部署配置

```python
# ============================================
# 生产级配置示例
# ============================================
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI

# PostgreSQL 持久化
checkpointer = PostgresSaver.from_conn_string(
    os.getenv("DATABASE_URL")
)

# 模型配置
llm = ChatOpenAI(
    model="gpt-4",
    temperature=0,
    max_tokens=4096,
    api_key=os.getenv("OPENAI_API_KEY")
)

# 工具节点配置
tools = [my_tool]
tool_node = ToolNode(tools)

# Agent 配置
agent = create_agent(
    llm=llm,
    tools=tools,
    checkpointer=checkpointer,
    state_schema=AgentState,
    interrupt_before=["human_review"]  # 关键步骤需要人工确认
)
```

### 5.5 安全与权限控制

```python
from deepagents.permissions import PermissionRule, PermissionScope

# 文件系统权限规则
permissions = [
    PermissionRule(
        scope=PermissionScope.ALLOW,
        path="/project/src/**",
        operations=["read", "write"]
    ),
    PermissionRule(
        scope=PermissionScope.DENY,
        path="/project/secrets/**",
        operations=["read", "write"]
    ),
    PermissionRule(
        scope=PermissionScope.ALLOW,
        path="/tmp/**",
        operations=["read", "write"]
    ),
]

# 创建带权限控制的 Agent
agent = create_deep_agent(
    model="openai:gpt-4",
    permissions=permissions
)
```

---

## 6. 最佳实践与反模式

### 6.1 工具设计原则

**ACI 原则**：

- **Action-oriented**：描述动作而非功能
- **Context-aware**：包含使用场景和反例
- **Structured output**：返回结构化数据而非原始内容

```python
# 差 ✗
def get_weather(city: str):
    """获取城市天气"""
    return api_call(city)

# 好 ✓
def get_weather(city: str) -> dict:
    """
    获取指定城市的当前天气。
    
    Use when: 用户询问特定城市的天气时
    Don't use when: 用户只是闲聊或询问预报
    
    Returns: {"temperature": int, "condition": str, "humidity": int}
    """
    data = api_call(city)
    return {
        "temperature": data["temp"],
        "condition": data["weather"],
        "humidity": data["humidity"]
    }
```

### 6.2 上下文分层管理

| 层级 | 内容 | 管理方式 |
|------|------|----------|
| 系统层 | 身份定义、绝对禁止 | 系统提示 |
| Skills 层 | 按需加载的技能 | 索引 + 延迟加载 |
| 运行时层 | 当前任务信息 | 自动注入 |
| 记忆层 | 跨会话经验 | 定期整合 |

### 6.3 常见反模式

| 反模式 | 问题 | 解决方案 |
|--------|------|----------|
| 单一长提示 | 关键信息被稀释 | 拆分为 Skills 按需加载 |
| 工具堆砌 | 选择困难 | 合并重叠工具，命名空间分组 |
| 无验证机制 | 无法确认完成 | 绑定可执行验收标准 |
| 状态放上下文 | 断点无法恢复 | 用 Checkpointer 外化 |
| 期望即约束 | 不确定性 | 用 Linter / Hook 强制 |

### 6.4 生产检查清单

- [ ] Checkpointer 配置完成（Postgres/Redis）
- [ ] LangSmith 追踪集成
- [ ] 错误处理链路完整
- [ ] 工具权限规则明确
- [ ] 评测数据集就绪
- [ ] 监控告警配置

---

## 附录：代码索引

| 场景 | 文件位置 | 说明 |
|------|----------|------|
| LangChain 简单 Agent | 2.3 节 | `create_agent` 示例 |
| LangGraph 代码开发流 | 3.3 节 | 完整工作流编排 |
| Checkpoint 持久化 | 3.4 节 | PostgresSaver |
| Human-in-the-loop | 3.5 节 | `interrupt` 机制 |
| Deep Agent 代码开发 | 4.3 节 | 完整代码开发 Agent |
| 数据处理 Pipeline | 4.4 节 | 完整数据处理 Agent |
| LangSmith 集成 | 5.2 节 | 可观测性配置 |
| 生产部署 | 5.4 节 | 配置模板 |

---

如需进一步深化特定章节或添加特定场景的代码示例，请告知。