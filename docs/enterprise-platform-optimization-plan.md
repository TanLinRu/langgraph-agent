# Enterprise Workflow Aggregation Platform - Optimization Plan

> Strategic plan to evolve langgraph-agent from a single-agent project into an enterprise-level personal workflow aggregation platform with rapid business automation embedding.

---

## 1. Current State Assessment

### Architecture Strengths

- LangGraph-native state machine with supervisor pattern (`create_supervisor` + `create_react_agent`)
- Clean module separation: registry, supervisor, event bus, sub-agent factory
- Real-time SSE event streaming to Vue 3 frontend
- Agent/graph CRUD with REST API
- ACP protocol for external tool integration (OpenCode CLI)

### Critical Gaps

| Gap | Current State | Impact |
|-----|--------------|--------|
| Auth/RBAC | Open CORS, no auth middleware | Cannot deploy beyond local dev |
| Execution persistence | Module-level dict, lost on restart | Unreliable for any real workflow |
| Plugin system | JSON blobs in flat files | No hot-reload, no versioning, no sandboxing |
| API design | 30+ unversioned endpoints | Fragile contract, no SDK generation |
| Multi-tenancy | Single global registry/event bus | Cannot serve multiple users |
| Observability | No structured logging or tracing | Cannot debug production issues |
| Frontend state | Per-store fetch() with no shared client | Error-prone, no retry/auth |

### Reference Platform Analysis

| Platform | Core Pattern | Extension Model | What We Can Borrow |
|----------|-------------|-----------------|-------------------|
| **n8n** | DAG + `INodeType` interface | npm community nodes, factory registry | Node interface contract, expression engine |
| **Dify** | DAG + GraphEngine + VariablePool | Node factory with versioning | VariablePool abstraction, layered execution pipeline |
| **Langflow** | Component graph with typed I/O | Python class auto-discovery | Self-describing node templates, type matching |
| **CrewAI** | Role-based crew + sequential/hierarchical | Tool callables on agents | Role/goal/backstory agent model, two orchestration modes |
| **AutoGen** | Actor model + topic pub/sub | Factory registration + decorators | Agent-level state serialization, topic subscriptions |
| **FastGPT** | DAG + dispatch switch | HTTP API plugins with OpenAPI | Dispatch router, variable passthrough |
| **Coze** | Bot = prompt + tools + workflows + KB | OAuth2 plugin API | Marketplace model, channel publishing |

---

## 2. Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Gateway Layer                         │
│  /api/v1/...  │  Auth + RBAC  │  Rate Limit  │  Request Valid.  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Chat Engine   │  │ Workflow     │  │ Agent Marketplace    │  │
│  │ (conversa-    │  │ Engine       │  │ (registry + version  │  │
│  │  tional)      │  │ (DAG exec)   │  │  + sandbox)          │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                  │                      │              │
│  ┌──────┴──────────────────┴──────────────────────┴───────────┐ │
│  │              Execution Runtime (LangGraph)                  │ │
│  │  Supervisor  │  Sub-agents  │  Tools  │  EventBus (SSE)    │ │
│  └──────────────┴──────────────┴─────────┴────────────────────┘ │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Skill Engine  │  │ Knowledge    │  │ Plugin System        │  │
│  │ (registry +   │  │ Base (RAG +  │  │ (hot-reload +        │  │
│  │  discovery)   │  │  memory)     │  │  versioning)         │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  Persistence Layer: SQLite/PostgreSQL + ChromaDB + Redis        │
└─────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Plugin-first**: Every business capability is a plugin (agent, skill, workflow template)
2. **Convention over configuration**: Sensible defaults, explicit overrides
3. **Observable by default**: Structured logging, tracing, metrics on every execution
4. **API contract stability**: Versioned endpoints, generated SDK, OpenAPI spec
5. **Progressive complexity**: Simple scripts -> workflows -> multi-agent crews -> distributed systems

---

## 3. Phased Roadmap

### Phase 1: Foundation Hardening (Weeks 1-3)

**Goal**: Make the platform production-deployable with clean API contracts.

#### 1.1 API Gateway & Auth

```
Changes:
├── server.py — add FastAPI middleware chain
│   ├── AuthMiddleware (JWT/API-key validation)
│   ├── RateLimitMiddleware (token bucket per-user)
│   ├── RequestValidationMiddleware (Pydantic models for all endpoints)
│   └── CORSMiddleware (restrict origins from config)
├── src/auth/ — new module
│   ├── models.py — User, Role, Permission models
│   ├── jwt.py — token generation/validation
│   └── rbac.py — role-based access control
└── All endpoints migrate to /api/v1/ prefix
```

**Key decisions**:
- API key auth for programmatic access, JWT for UI sessions
- Roles: `admin`, `operator`, `viewer` (maps to agent/workflow CRUD permissions)
- SQLite for user store (matches existing memory/ pattern), migrate path to PostgreSQL later

#### 1.2 Execution State Persistence

```python
# Replace module-level dict with persistence
class ExecutionStore:
    """Backed by SQLite (same DB as user store)."""
    def save_execution(self, exec: ExecutionRecord) -> None: ...
    def get_execution(self, id: str) -> ExecutionRecord | None: ...
    def list_executions(self, filters: ExecutionFilters) -> list[ExecutionRecord]: ...
    def update_status(self, id: str, status: str, result: dict) -> None: ...
```

**Inspiration**: AutoGen's `save_state()` / `load_state()` per-agent pattern. Each sub-agent serializes its own state; the supervisor aggregates.

#### 1.3 Shared Frontend API Client

```typescript
// ui/src/api/client.ts
class ApiClient {
  constructor(private baseUrl: string, private auth: AuthProvider) {}

  async request<T>(path: string, options?: RequestOptions): Promise<ApiResponse<T>> {
    // - JWT injection
    // - Retry with exponential backoff
    // - Error normalization
    // - Request cancellation via AbortController
    // - Loading state integration with Pinia
  }
}
```

Replace all per-store `fetch()` calls with this shared client.

#### 1.4 Structured Logging & Observability

```python
import structlog

logger = structlog.get_logger()

# In supervisor.py
logger.info("execution_started",
    execution_id=exec_id,
    graph_id=graph_id,
    agent_count=len(agents),
    user_id=current_user.id
)

# OpenTelemetry tracing
from opentelemetry import trace
tracer = trace.get_tracer("langgraph-agent")

@tracer.start_as_current_span("supervisor.run")
async def run(self, graph_id, input_text, thread_id):
    span = trace.get_current_span()
    span.set_attribute("graph.id", graph_id)
    ...
```

**Deliverables**:
- [ ] Auth middleware with JWT + API key support
- [ ] RBAC with admin/operator/viewer roles
- [ ] All endpoints under `/api/v1/` with Pydantic request/response models
- [ ] Execution state persisted to SQLite
- [ ] Shared `ApiClient` in frontend replacing all raw fetch calls
- [ ] structlog + OpenTelemetry integration

---

### Phase 2: Plugin System & Business Module Architecture (Weeks 4-6)

**Goal**: Any new business capability can be added as a self-contained plugin without modifying core code.

#### 2.1 Plugin Interface

Inspired by n8n's `INodeType` and Dify's node factory pattern:

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel

class PluginManifest(BaseModel):
    """Self-describing plugin metadata."""
    name: str                          # e.g., "email-automation"
    version: str                       # semver
    description: str
    author: str
    capabilities: list[str]            # ["tool", "agent", "workflow_template", "trigger"]
    dependencies: list[str]            # other plugin names
    config_schema: dict                # JSON Schema for plugin config

class Plugin(ABC):
    """Base class for all plugins."""

    @abstractmethod
    def manifest(self) -> PluginManifest: ...

    def on_activate(self, ctx: PluginContext) -> None:
        """Called when plugin is loaded. Register tools, agents, routes."""
        pass

    def on_deactivate(self) -> None:
        """Called when plugin is unloaded. Clean up resources."""
        pass
```

#### 2.2 Plugin Discovery & Loading

```
plugins/
├── builtin/
│   ├── code-execution/          # existing tools
│   │   ├── __init__.py          # Plugin subclass
│   │   ├── manifest.json        # auto-generated from PluginManifest
│   │   └── tools/               # tool implementations
│   ├── email-automation/
│   │   ├── __init__.py
│   │   ├── agent.py             # email agent definition
│   │   ├── tools.py             # send_email, read_inbox tools
│   │   └── workflows/           # predefined workflow templates
│   └── data-pipeline/
│       ├── __init__.py
│       ├── tools.py             # etl tools
│       └── triggers/            # cron, webhook triggers
├── community/                   # third-party plugins
│   └── jira-integration/
└── _loader.py                   # discovery + hot-reload
```

**Discovery**: Scan `plugins/` directory on startup. Hot-reload via watchdog file system monitor (optional, config-gated).

**Inspiration**: n8n's `NodeType` registry + Dify's `DifyNodeFactory` version resolution.

#### 2.3 VariablePool for Workflow Data Flow

Replace the current flat variable passing with Dify's decoupled pattern:

```python
class VariablePool:
    """Shared namespace for workflow node outputs.

    Nodes write: pool.set("node_1", "result", data)
    Nodes read:  pool.get("node_1", "result") or pool.get(["node_1", "result"])
    """
    _data: dict[str, dict[str, Any]]

    def set(self, node_id: str, key: str, value: Any) -> None: ...
    def get(self, selector: str | list[str]) -> Any: ...
    def snapshot(self) -> dict: ...  # for persistence/replay
```

#### 2.4 Business Module Template

For rapid "business automation embedding", provide a scaffold:

```bash
python -m scripts.create_plugin --name order-processing --type workflow

# Generates:
plugins/order-processing/
├── __init__.py          # Plugin class with on_activate()
├── manifest.json        # name, version, capabilities
├── agent.py             # optional: dedicated agent
├── tools/
│   ├── validate_order.py
│   ├── process_payment.py
│   └── notify_customer.py
├── workflows/
│   └── order_flow.json  # DAG definition
├── triggers/
│   └── webhook.py       # HTTP trigger endpoint
├── config_schema.json   # plugin configuration
└── tests/
    └── test_order_flow.py
```

**Key pattern**: The plugin's `on_activate()` registers its tools into the global tool registry, its agents into the agent registry, and its workflow templates into the workflow registry. The core engine doesn't need to know about any specific business domain.

**Deliverables**:
- [ ] `Plugin` base class + `PluginManifest` model
- [ ] Plugin loader with directory scanning and hot-reload
- [ ] `VariablePool` replacing flat variable passing in workflows
- [ ] `create_plugin` scaffold script
- [ ] Migrate existing tools/skills into 2-3 builtin plugins as proof of concept

---

### Phase 3: Workflow Engine Upgrade (Weeks 7-9)

**Goal**: Support parallel branches, conditional routing, loops, and sub-workflow composition.

#### 3.1 DAG Executor with Layered Pipeline

Inspired by Dify's GraphEngine:

```python
class WorkflowEngine:
    """DAG workflow executor with composable execution layers."""

    def __init__(self, layers: list[ExecutionLayer] | None = None):
        self.layers = layers or []

    async def execute(self, graph: WorkflowGraph, variables: VariablePool) -> WorkflowResult:
        for node in graph.topological_order():
            # Pre-execution layers (limits, logging, quota)
            for layer in self.layers:
                await layer.before_node(node, variables)

            result = await self._execute_node(node, variables)
            variables.set(node.id, "output", result)

            # Post-execution layers (metrics, checkpoint)
            for layer in self.layers:
                await layer.after_node(node, result, variables)

        return WorkflowResult(variables=variables)

class ExecutionLayer(ABC):
    """Composable execution concern."""
    async def before_node(self, node, variables): ...
    async def after_node(self, node, result, variables): ...

# Concrete layers
class LoggingLayer(ExecutionLayer): ...
class LimitsLayer(ExecutionLayer):    # max steps, timeout
class CheckpointLayer(ExecutionLayer): # persist per-node output
class MetricsLayer(ExecutionLayer):    # timing, token usage
```

#### 3.2 Enhanced Node Types

Current `workflows.json` supports only `skill` and `dispatch`. Add:

| Node Type | Description | Inspired By |
|-----------|-------------|-------------|
| `llm` | Direct LLM call with prompt template | Dify, FastGPT |
| `condition` | If/else branching on expression | Dify `if_else`, n8n IF node |
| `parallel` | Fan-out to multiple branches, fan-in | FastGPT `parallelRun` |
| `loop` | Iterate over collection | FastGPT `loop` |
| `sub_workflow` | Invoke another workflow as a node | n8n sub-workflow |
| `human_input` | Pause execution, wait for user input | Dify `question` node |
| `webhook` | Trigger via HTTP webhook | n8n webhook trigger |
| `cron` | Trigger on schedule | n8n cron trigger |

#### 3.3 Workflow Visual Builder Upgrade

Current VueFlow canvas needs:
- Node palette (drag-and-drop from sidebar)
- Edge validation (type-compatible connections only)
- Node configuration panel (form per node type, auto-generated from schema)
- Execution replay (step through VariablePool state)
- Parallel branch visualization

**Deliverables**:
- [ ] `WorkflowEngine` with `ExecutionLayer` pipeline
- [ ] 8 node types with handler implementations
- [ ] `VariablePool` integration with workflow engine
- [ ] Per-node checkpointing for execution replay
- [ ] VueFlow node palette + configuration panel

---

### Phase 4: Multi-Agent Orchestration Patterns (Weeks 10-12)

**Goal**: Support hierarchical, sequential, and hybrid orchestration patterns beyond simple supervisor routing.

#### 4.1 Orchestration Modes

Inspired by CrewAI's two modes + AutoGen's actor model:

```python
class OrchestrationMode(Enum):
    SEQUENTIAL = "sequential"    # tasks in order (current default)
    HIERARCHICAL = "hierarchical" # manager delegates to workers
    PARALLEL = "parallel"        # independent tasks concurrently
    CONVERSATIONAL = "conversational" # agents discuss until consensus
    PIPELINE = "pipeline"        # output of one feeds into next

class CrewDefinition(BaseModel):
    """Multi-agent team definition."""
    name: str
    agents: list[AgentRole]       # role, goal, backstory, tools
    tasks: list[TaskDefinition]   # description, expected_output, assigned_agent
    mode: OrchestrationMode
    max_iterations: int = 10
    consensus_threshold: float = 0.8  # for conversational mode
```

#### 4.2 Agent Communication Protocol

Borrow AutoGen's topic-based pub/sub for inter-agent messaging:

```python
class AgentMessageBus:
    """Topic-based message routing between agents."""

    def subscribe(self, agent_id: str, topic: str) -> None: ...
    def unsubscribe(self, agent_id: str, topic: str) -> None: ...
    async def publish(self, topic: str, message: AgentMessage) -> None: ...
    async def request(self, target_agent: str, message: AgentMessage) -> AgentMessage: ...
```

This enables patterns like:
- Manager broadcasts task, workers respond with proposals
- Agents form ad-hoc teams on specific topics
- Human-in-the-loop as a special "agent" subscribed to intervention topics

#### 4.3 Agent Marketplace

```
marketplace/
├── featured/                    # curated agents
│   ├── code-reviewer/
│   ├── data-analyst/
│   └── email-writer/
├── community/                   # user-contributed
│   ├── jira-bot/
│   └── slack-assistant/
└── templates/                   # crew templates
    ├── dev-team.json            # code + review + deploy crew
    ├── content-team.json        # research + write + edit crew
    └── support-team.json        # triage + respond + escalate crew
```

Each marketplace entry:
- Self-contained plugin (Phase 2)
- Versioned with semver
- Rating/usage metadata
- One-click install into user's workspace

**Deliverables**:
- [ ] `CrewDefinition` model with 5 orchestration modes
- [ ] `AgentMessageBus` for inter-agent communication
- [ ] Conversational mode with consensus detection
- [ ] Crew templates (3+ predefined team compositions)
- [ ] Marketplace REST API (list, install, rate)

---

### Phase 5: Rapid Business Automation Embedding (Weeks 13-15)

**Goal**: New business processes can be automated in hours, not days.

#### 5.1 Business Module SDK

```python
from langgraph_agent import Plugin, tool, agent, workflow, trigger

class OrderProcessing(Plugin):
    name = "order-processing"
    version = "1.0.0"

    @tool
    def validate_order(self, order_data: dict) -> dict:
        """Validate order fields and business rules."""
        ...

    @tool
    def process_payment(self, amount: float, method: str) -> dict:
        """Process payment via payment gateway."""
        ...

    @agent(
        role="Order Processor",
        goal="Process customer orders efficiently",
        tools=["validate_order", "process_payment"]
    )
    def order_agent(self): ...

    @workflow
    def order_flow(self):
        return {
            "nodes": [
                {"id": "validate", "type": "tool", "tool": "validate_order"},
                {"id": "check_inventory", "type": "tool", "tool": "check_stock"},
                {"id": "payment", "type": "tool", "tool": "process_payment"},
                {"id": "notify", "type": "tool", "tool": "send_notification"},
            ],
            "edges": [
                {"from": "validate", "to": "check_inventory"},
                {"from": "check_inventory", "to": "payment"},
                {"from": "payment", "to": "notify"},
            ],
            "triggers": [
                {"type": "webhook", "path": "/api/v1/orders"},
                {"type": "cron", "schedule": "0 9 * * 1-5"},
            ]
        }
```

#### 5.2 One-Command Business Module Creation

```bash
# Create a new business automation module
python -m langgraph_agent.scaffold create \
  --name "customer-support" \
  --triggers "webhook,cron" \
  --agents "triage-agent,resolution-agent" \
  --tools "check_ticket,send_reply,escalate" \
  --workflow "triage -> resolve -> notify"

# Generates complete plugin structure with tests, docs, and CI config
```

#### 5.3 Integration Patterns

| Pattern | Use Case | Implementation |
|---------|----------|---------------|
| **Webhook trigger** | External system pushes events | FastAPI endpoint per plugin |
| **Polling trigger** | Periodic check for changes | Cron scheduler + plugin poll method |
| **Event trigger** | Internal EventBus subscription | Plugin subscribes to EventBus topics |
| **User trigger** | Manual invocation from UI | Plugin registers UI action |
| **API trigger** | External API call | Standard REST endpoint |

#### 5.4 Template Library

Pre-built workflow templates for common business domains:

| Domain | Template | Agents | Tools |
|--------|----------|--------|-------|
| Customer Support | ticket-triage | classifier, responder, escalator | check_ticket, send_reply, create_escalation |
| Content Production | content-pipeline | researcher, writer, editor, publisher | search, write_draft, review, publish |
| Data Processing | etl-pipeline | extractor, transformer, loader | query_db, transform, load_to_db |
| Code Review | review-flow | analyzer, reviewer, fixer | read_code, suggest_fix, apply_patch |
| Sales Operations | lead-qualification | scorer, enricher, notifier | score_lead, enrich_data, send_email |

**Deliverables**:
- [ ] Plugin SDK with `@tool`, `@agent`, `@workflow`, `@trigger` decorators
- [ ] `scaffold` CLI for one-command module creation
- [ ] 5+ business domain templates
- [ ] Integration pattern implementations (webhook, polling, event, API)
- [ ] Template gallery in frontend UI

---

### Phase 6: Enterprise Features (Weeks 16-18)

**Goal**: Production-grade features for team deployment.

#### 6.1 Multi-Tenancy

```
Tenant isolation:
├── Registry: tenant-scoped agent/workflow storage
├── EventBus: tenant-filtered event streams
├── Execution: tenant-pinned execution contexts
└── Storage: tenant-schema in PostgreSQL (or tenant-prefixed SQLite tables)
```

#### 6.2 Advanced Observability

- Execution trace visualization (DAG with per-node timing)
- Token usage dashboards per agent/workflow/user
- Error rate monitoring with alerting
- Cost estimation and budget limits

#### 6.3 Deployment & Scaling

```
Docker Compose (single-node):
├── app (FastAPI + Vue static)
├── redis (execution queue + caching)
├── postgres (persistence)
└── chromadb (vector memory)

Kubernetes (multi-node):
├── api-deployment (stateless, horizontal scale)
├── worker-deployment (execution runtime)
├── redis-cluster
├── postgres-ha
└── chromadb-cluster
```

**Deliverables**:
- [ ] Tenant isolation across all subsystems
- [ ] Execution trace visualization in dashboard
- [ ] Token/cost tracking and budget limits
- [ ] Docker Compose for single-node deployment
- [ ] Kubernetes Helm chart for multi-node deployment

---

## 4. Implementation Priority Matrix

| Phase | Effort | Impact | Dependency | Priority |
|-------|--------|--------|------------|----------|
| 1. Foundation | Medium | High | None | **P0** |
| 2. Plugin System | Medium | High | Phase 1 | **P0** |
| 3. Workflow Engine | High | High | Phase 2 | **P1** |
| 4. Multi-Agent Patterns | Medium | Medium | Phase 2 | **P1** |
| 5. Business SDK | Medium | High | Phases 2+3 | **P1** |
| 6. Enterprise Features | High | Medium | All above | **P2** |

**Phase 1 + 2 are the critical path.** They unblock everything else and deliver the most value: a deployable platform with a plugin architecture that enables rapid business module creation.

---

## 5. Key Architectural Decisions

### Decision 1: SQLite -> PostgreSQL Migration Path

- **Now**: SQLite for zero-config local development (matches existing `memory/` pattern)
- **Later**: PostgreSQL for multi-tenant production (SQLAlchemy abstracts the difference)
- **Migration**: Alembic for schema migrations, single config switch

### Decision 2: Keep LangGraph as Core Runtime

- All orchestration modes ultimately compile to LangGraph `StateGraph`
- Supervisor pattern for LLM-routed delegation
- Custom `StateGraph` builders for sequential/parallel/pipeline modes
- This gives us LangGraph Studio compatibility for all execution types

### Decision 3: Plugin System Over Monolith Extension

- Every new business capability is a plugin, not a core module addition
- Core provides: engine, registry, event bus, auth, API gateway
- Plugins provide: domain-specific tools, agents, workflows, triggers
- This keeps the core stable while enabling unlimited domain expansion

### Decision 4: Frontend Component Architecture

- Keep Vue 3 + Pinia (already established)
- Add: shared API client, component library (headless UI), design tokens
- Dashboard panels become plugin-extensible (plugins can register UI panels)
- VueFlow canvas enhanced with plugin-contributed node types

### Decision 5: Event-Driven Communication

- EventBus becomes the backbone for all cross-component communication
- Plugins subscribe to events they care about
- SSE for frontend real-time updates (already implemented)
- Future: optional message queue (Redis Streams) for distributed deployment

---

## 6. Success Metrics

| Metric | Current | Phase 1-2 Target | Phase 3-5 Target | Phase 6 Target |
|--------|---------|-------------------|-------------------|----------------|
| Time to add new business automation | N/A (manual) | 2-3 days | 2-4 hours | < 1 hour |
| Workflow node types | 2 (skill, dispatch) | 2 + plugin system | 10+ | 15+ |
| Orchestration patterns | 1 (sequential) | 1 (supervisor) | 5 | 5 + custom |
| Concurrent executions | ~1 (in-memory) | 10+ (persisted) | 100+ (queued) | 1000+ |
| Authenticated users | 0 | 1-5 | 10-50 | 100+ |
| Observability | None | Structured logs | Traces + metrics | Full dashboards |
| Plugin ecosystem | 0 | 3 builtin | 10 builtin + community | 30+ |

---

## 7. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Plugin API instability | High | Medium | Versioned plugin interfaces, deprecation warnings, migration guides |
| Performance regression with persistence | Medium | High | Async writes, connection pooling, benchmark suite |
| Frontend complexity explosion | Medium | Medium | Component library, design system, lazy loading |
| LangGraph version breaking changes | Low | High | Pin versions, abstract LangGraph behind internal interface |
| Scope creep | High | High | Strict phase boundaries, ship-and-iterate approach |

---

## 8. Quick Wins (Immediate Next Steps)

These can be done in the current session without waiting for the full plan:

1. **Clean up dead code**: Remove `orchestrator.py` import from `server.py` (line 110), mark as deprecated
2. **API versioning prefix**: Add `/api/v1/` alias for all current endpoints (backward-compatible)
3. **Shared fetch client**: Create `ui/src/api/client.ts` with error normalization
4. **Execution state SQLite**: Move `_supervisor_executions` dict to SQLite table
5. **Plugin manifest model**: Define `PluginManifest` Pydantic model (foundation for Phase 2)
