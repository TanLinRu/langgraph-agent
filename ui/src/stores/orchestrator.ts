import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Node, Edge } from '@vue-flow/core'
import type { OrchestratorStep, OrchestratorState } from '../types'

export const useOrchestratorStore = defineStore('orchestrator', () => {
  const isOpen = ref(true)
  const currentState = ref<OrchestratorState | null>(null)
  const flowNodes = ref<Node[]>([])
  const flowEdges = ref<Edge[]>([])
  const selectedStepId = ref<string | null>(null)
  const loading = ref(false)
  const error = ref('')
  const replanProposal = ref<{ reason: string; new_steps: any[] } | null>(null)

  const selectedStep = computed(() => {
    if (!currentState.value || !selectedStepId.value) return null
    return currentState.value.steps.find(s => s.step_id === selectedStepId.value) || null
  })

  const statusLabel = computed(() => {
    const map: Record<string, string> = {
      planning: '规划中',
      running: '执行中',
      completed: '已完成',
      failed: '失败',
      rolled_back: '已回退',
    }
    return map[currentState.value?.status || ''] || ''
  })

  async function startOrchestration(message: string, threadId: string): Promise<string> {
    loading.value = true
    error.value = ''
    replanProposal.value = null
    selectedStepId.value = null

    try {
      const res = await fetch('/api/orchestrate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, thread_id: threadId }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      return data.orchestration_id
    } catch (e: any) {
      error.value = e.message || 'Failed to start orchestration'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function fetchState(orchestrationId: string): Promise<void> {
    try {
      const res = await fetch(`/api/orchestrate/${orchestrationId}/state`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      currentState.value = data
      updateFlowGraph(data.steps)
    } catch (e: any) {
      error.value = e.message || 'Failed to fetch state'
    }
  }

  async function rollback(orchestrationId: string, stepId: string, reason = ''): Promise<void> {
    try {
      const res = await fetch(`/api/orchestrate/${orchestrationId}/rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_id: stepId, reason }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      // State will be updated via SSE step_update events
    } catch (e: any) {
      error.value = e.message || 'Rollback failed'
    }
  }

  async function approveReplan(orchestrationId: string, approved = true): Promise<void> {
    try {
      const res = await fetch(`/api/orchestrate/${orchestrationId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      if (approved) {
        replanProposal.value = null
      }
    } catch (e: any) {
      error.value = e.message || 'Approve failed'
    }
  }

  // ========== SSE Event Handlers ==========

  function handleWorkflowPlan(data: Record<string, unknown>) {
    const steps = (data.steps as any[]) || []
    currentState.value = {
      orchestration_id: data.orchestration_id as string,
      thread_id: '',
      input_text: '',
      plan_summary: data.plan_summary as string || '',
      steps: steps.map(mapStepFromApi),
      status: 'running',
      created_at: '',
      updated_at: '',
      replan_count: 0,
    }
    // Use Vue Flow nodes/edges from backend if available
    if (data.vue_flow_nodes && data.vue_flow_edges) {
      flowNodes.value = (data.vue_flow_nodes as any[]).map((n: any) => ({
        ...n,
        type: 'orchestrator',
      }))
      flowEdges.value = (data.vue_flow_edges as any[]) as Edge[]
    } else {
      updateFlowGraph(currentState.value.steps)
    }
  }

  function handleStepUpdate(data: Record<string, unknown>) {
    if (!currentState.value) return
    const stepId = data.step_id as string
    const idx = currentState.value.steps.findIndex(s => s.step_id === stepId)
    if (idx === -1) return

    // Update step in place (immutable pattern: new array)
    const updatedSteps = [...currentState.value.steps]
    updatedSteps[idx] = {
      ...updatedSteps[idx],
      status: data.status as OrchestratorStep['status'],
      result: data.result as string | undefined,
      error: data.error as string | undefined,
      started_at: data.started_at as string | undefined,
      completed_at: data.completed_at as string | undefined,
      duration_ms: (data.duration_ms as number) || updatedSteps[idx].duration_ms,
    }
    currentState.value = { ...currentState.value, steps: updatedSteps }

    // Update the corresponding Vue Flow node
    const nodeIdx = flowNodes.value.findIndex(n => n.id === stepId)
    if (nodeIdx !== -1) {
      const updatedNodes = [...flowNodes.value]
      updatedNodes[nodeIdx] = {
        ...updatedNodes[nodeIdx],
        data: { ...updatedNodes[nodeIdx].data, ...data },
      }
      flowNodes.value = updatedNodes
    }

    // Auto-update edge animations for running steps
    updateEdgeAnimations()
  }

  function handleWorkflowReplan(data: Record<string, unknown>) {
    replanProposal.value = {
      reason: data.reason as string || '',
      new_steps: (data.new_steps as any[]) || [],
    }
  }

  function handleWorkflowComplete(data: Record<string, unknown>) {
    if (!currentState.value) return
    currentState.value = {
      ...currentState.value,
      status: (data.status as string) || 'completed',
      final_output: data.final_output as string || '',
    }
  }

  // ========== Graph Layout ==========

  function updateFlowGraph(steps: OrchestratorStep[]) {
    if (!steps.length) {
      flowNodes.value = []
      flowEdges.value = []
      return
    }

    // Compute depth for each step
    const depthMap = computeDepth(steps)
    const depthCounters: Record<number, number> = {}

    const nodes: Node[] = steps.map(step => {
      const depth = depthMap[step.step_id] || 0
      const row = depthCounters[depth] || 0
      depthCounters[depth] = row + 1

      return {
        id: step.step_id,
        type: 'orchestrator',
        position: { x: depth * 280, y: row * 140 },
        data: {
          step_id: step.step_id,
          agent_name: step.agent_name,
          description: step.description,
          status: step.status,
          result: step.result,
          error: step.error,
          duration_ms: step.duration_ms,
        },
      }
    })

    const edges: Edge[] = []
    for (const step of steps) {
      for (const depId of step.depends_on) {
        edges.push({
          id: `${depId}-${step.step_id}`,
          source: depId,
          target: step.step_id,
          type: 'smoothstep',
          animated: false,
        })
      }
    }

    flowNodes.value = nodes
    flowEdges.value = edges
  }

  function computeDepth(steps: OrchestratorStep[]): Record<string, number> {
    const depth: Record<string, number> = {}
    const stepMap = new Map(steps.map(s => [s.step_id, s]))

    function dfs(sid: string): number {
      if (sid in depth) return depth[sid]
      const step = stepMap.get(sid)
      if (!step || !step.depends_on.length) {
        depth[sid] = 0
        return 0
      }
      const maxDep = Math.max(...step.depends_on.map(d => dfs(d)))
      depth[sid] = maxDep + 1
      return depth[sid]
    }

    for (const step of steps) {
      dfs(step.step_id)
    }
    return depth
  }

  function updateEdgeAnimations() {
    if (!currentState.value) return
    const stepMap = new Map(currentState.value.steps.map(s => [s.step_id, s]))
    flowEdges.value = flowEdges.value.map(edge => {
      const targetStep = stepMap.get(edge.target)
      return {
        ...edge,
        animated: targetStep?.status === 'running',
      }
    })
  }

  function selectStep(stepId: string | null) {
    selectedStepId.value = stepId
  }

  function toggleSidebar() {
    isOpen.value = !isOpen.value
  }

  function mapStepFromApi(raw: any): OrchestratorStep {
    return {
      step_id: raw.step_id,
      agent_id: raw.agent_id,
      agent_name: raw.agent_name,
      description: raw.description,
      depends_on: raw.depends_on || [],
      status: raw.status,
      result: raw.result,
      error: raw.error,
      started_at: raw.started_at,
      completed_at: raw.completed_at,
      duration_ms: raw.duration_ms || 0,
    }
  }

  return {
    isOpen,
    currentState,
    flowNodes,
    flowEdges,
    selectedStepId,
    selectedStep,
    statusLabel,
    loading,
    error,
    replanProposal,
    startOrchestration,
    fetchState,
    rollback,
    approveReplan,
    handleWorkflowPlan,
    handleStepUpdate,
    handleWorkflowReplan,
    handleWorkflowComplete,
    updateFlowGraph,
    selectStep,
    toggleSidebar,
  }
})
