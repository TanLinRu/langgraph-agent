// ========== Chat ==========

// 工具调用状态
export type ToolStatus = 'pending' | 'running' | 'success' | 'error'

// 单个工具调用
export interface ToolInvocation {
  id: string
  name: string
  arguments: Record<string, unknown>
  status: ToolStatus
  result?: string
  startedAt?: string
  completedAt?: string
  duration?: number
  error?: string
}

// 执行步骤（用于图展示）
export interface ExecutionStep {
  stepId: number
  agentId: string
  agentName: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  startedAt?: string
  completedAt?: string
  result?: string
  error?: string
}

// 执行图数据（Vue Flow 格式）
export interface FlowNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: {
    label: string
    status: string
    agent_id?: string
  }
  style?: Record<string, string>
}

export interface FlowEdge {
  id: string
  source: string
  target: string
  type?: string
  animated?: boolean
  style?: Record<string, string>
}

export interface ExecutionGraphData {
  execution_id: string
  graph_id: string
  status: string
  nodes: FlowNode[]
  edges: FlowEdge[]
}

// 指标数据
export interface TurnMetric {
  turn: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  cost_usd: number
  elapsed_sec: number
}

export interface ExecutionMetrics {
  total_requests?: number
  total_tokens?: number
  total_cost_usd?: number
  total_latency_sec?: number
  avg_latency_sec?: number
  tool_calls?: number
  compressions?: number
  turns?: TurnMetric[]
}

export interface ToolCall {
  name: string
  arguments?: unknown
  result?: string
}

export interface Message {
  role: string
  content: string
  tool_calls?: ToolCall[] | null
}

// 增强的 ChatTurn
export interface ChatTurn {
  id: number
  userMessage: string
  reply: string
  messages: Message[]
  tool_calls: ToolCall[] | null
  toolInvocations: ToolInvocation[]      // 增强：工具调用详情
  executionSteps: ExecutionStep[]       // 增强：执行步骤
  executionGraph?: ExecutionGraphData  // 增强：执行图
  metrics: ExecutionMetrics
  compression_count: number | null
  elapsed_sec: number
  expanded: boolean
}

export interface Session {
  thread_id: string
  preview: string
  metadata: any
  updated_at: string
}

// ========== Skills ==========

export interface Skill {
  name: string
  description: string
  use_when: string[]
  dont_use_when: string[]
  full_content?: string
}

// ========== Workflows ==========

export interface Workflow {
  id: string
  name: string
  description: string
  nodes: any[]
  edges: any[]
  created_at: string
  updated_at: string
}

// ========== Agents ==========

export interface AgentDef {
  id: string
  name: string
  description: string
  llm_model: string
  tools: string[]
  execution_mode: string
  timeout: number
  is_builtin: boolean
  created_at?: string
  updated_at?: string
  system_prompt?: string
  skill_source?: string
}

export interface AgentGraph {
  id: string
  name: string
  description: string
  nodes: any[]
  edges: any[]
  parallel_groups: any[]
  config: any
  created_at?: string
  updated_at?: string
}

// ========== CLI ==========

export interface CliInfo {
  name: string
  path: string
  available: boolean
  modes: string[]
  capabilities: string[]
  description: string
}

export interface CliTask {
  id: string
  cli_name: string
  task: string
  working_dir: string
  mode: string
  result: any
  created_at: string
}

export interface StreamStep {
  id: number
  text: string
  toolCalls: Array<{
    tool: string
    input: Record<string, unknown>
    output: string
    title?: string
  }>
  tokens?: { total: number; input: number; output: number }
  cost?: number
  reason?: string
  isComplete: boolean
}

export interface StreamParsedResult {
  steps: StreamStep[]
  finalText: string
  totalTokens: number
  totalCost: number
}

// ========== SOP ==========

export interface SOPStateInfo {
  file: string
  sop: string
  date: string
}

export interface SOPStateDetail {
  task_id: string
  sop: string
  status: string
  started_at: string
  current_step: number
  steps: Record<string, { status: string; timestamp?: string }>
  answers: Record<string, Record<string, unknown>>
}

// ========== Dashboard (Phase 3) ==========

export interface AgentActivity {
  agent_id: string
  agent_name: string
  status: 'idle' | 'running' | 'completed' | 'failed'
  started_at?: string
  finished_at?: string
  result_summary?: string
}

export interface SkillTrigger {
  skill_name: string
  triggered_at: string
  context?: string
}

export interface TaskProgress {
  execution_id: string
  current_step: number
  total_steps: number
  status: string
  started_at: string
}

export interface Observation {
  id: number
  event_type: string
  data: Record<string, unknown>
  timestamp: string
}

// ========== Tabs ==========

export type TabId = 'chat' | 'agents' | 'skills' | 'workflows' | 'cli' | 'sop'

export interface TabDef {
  id: TabId
  label: string
  icon: string
}

// ========== Dynamic Orchestrator ==========

export interface OrchestratorStep {
  step_id: string
  agent_id: string
  agent_name: string
  description: string
  depends_on: string[]
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  result?: string
  error?: string
  started_at?: string
  completed_at?: string
  duration_ms: number
}

export interface OrchestratorState {
  orchestration_id: string
  thread_id: string
  input_text: string
  plan_summary: string
  steps: OrchestratorStep[]
  status: 'planning' | 'running' | 'completed' | 'failed' | 'rolled_back'
  current_step_id?: string
  final_output?: string
  created_at: string
  updated_at: string
  replan_count: number
}
