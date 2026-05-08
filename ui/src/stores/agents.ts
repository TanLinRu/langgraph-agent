import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AgentDef, AgentGraph } from '../types'

export const useAgentsStore = defineStore('agents', () => {
  const agents = ref<AgentDef[]>([])
  const agentGraphs = ref<AgentGraph[]>([])
  const loading = ref(false)
  const selectedAgent = ref<AgentDef | null>(null)
  const showAgentModal = ref(false)
  const editingAgentId = ref('')
  const agentForm = ref({
    name: '',
    description: '',
    llm_model: 'openai:gpt-4',
    system_prompt: '',
    tools: [] as string[],
    execution_mode: 'sync',
    timeout: 60,
  })

  // Execution state
  const executionPlan = ref<any>(null)
  const currentExecution = ref<any>(null)
  const executionLoading = ref(false)
  const showPlanApproval = ref(false)
  const executionInput = ref('')
  const nodeStatuses = ref<Record<string, 'pending' | 'running' | 'completed' | 'failed'>>({})
  const showExecutionDetail = ref(false)
  const executionReport = ref<any>(null)
  const selectedAgentGraph = ref('')

  async function loadAgents() {
    loading.value = true
    try {
      const res = await fetch('/api/agents')
      const data = await res.json()
      agents.value = data.agents || []
    } catch (e) {
      console.error('Failed to load agents:', e)
    } finally {
      loading.value = false
    }
  }

  async function loadAgentGraphs() {
    loading.value = true
    try {
      const res = await fetch('/api/agent-graphs')
      const data = await res.json()
      agentGraphs.value = data.graphs || []
    } catch (e) {
      console.error('Failed to load agent graphs:', e)
    } finally {
      loading.value = false
    }
  }

  async function createAgent() {
    if (!agentForm.value.name.trim()) {
      alert('请输入 Agent 名称')
      return
    }
    try {
      const res = await fetch('/api/agents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(agentForm.value),
      })
      const data = await res.json()
      if (data.status === 'success') {
        showAgentModal.value = false
        await loadAgents()
        resetAgentForm()
      }
    } catch (e) {
      console.error('Failed to create agent:', e)
    }
  }

  async function updateAgent() {
    if (!editingAgentId.value || !agentForm.value.name.trim()) return
    try {
      const res = await fetch(`/api/agents/${editingAgentId.value}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(agentForm.value),
      })
      const data = await res.json()
      if (data.status === 'success') {
        showAgentModal.value = false
        await loadAgents()
        resetAgentForm()
      }
    } catch (e) {
      console.error('Failed to update agent:', e)
    }
  }

  async function deleteAgent(id: string) {
    if (!confirm('确定删除此 Agent?')) return
    try {
      await fetch(`/api/agents/${id}`, { method: 'DELETE' })
      await loadAgents()
    } catch (e) {
      console.error('Failed to delete agent:', e)
    }
  }

  function openNewAgent() {
    editingAgentId.value = ''
    resetAgentForm()
    showAgentModal.value = true
  }

  function openEditAgent(agent: AgentDef) {
    if (agent.is_builtin) {
      alert('内置 Agent 不能编辑')
      return
    }
    editingAgentId.value = agent.id
    agentForm.value = {
      name: agent.name,
      description: agent.description,
      llm_model: agent.llm_model,
      system_prompt: agent.system_prompt || '',
      tools: agent.tools || [],
      execution_mode: agent.execution_mode,
      timeout: agent.timeout,
    }
    showAgentModal.value = true
  }

  function resetAgentForm() {
    agentForm.value = {
      name: '',
      description: '',
      llm_model: 'openai:gpt-4',
      system_prompt: '',
      tools: [],
      execution_mode: 'sync',
      timeout: 60,
    }
  }

  async function generatePlan() {
    if (!executionInput.value.trim()) {
      alert('请输入任务描述')
      return
    }
    if (!selectedAgentGraph.value) {
      alert('请选择 Agent Graph')
      return
    }
    executionLoading.value = true
    try {
      const res = await fetch('/api/execution/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          graph_id: selectedAgentGraph.value,
          input_text: executionInput.value,
        }),
      })
      executionPlan.value = await res.json()
      showPlanApproval.value = true
    } catch (e) {
      console.error('Failed to generate plan:', e)
    } finally {
      executionLoading.value = false
    }
  }

  async function runWithApproval() {
    if (!selectedAgentGraph.value || !executionInput.value.trim()) return
    executionLoading.value = true
    try {
      const res = await fetch('/api/execution/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          graph_id: selectedAgentGraph.value,
          input_text: executionInput.value,
          approved: true,
        }),
      })
      currentExecution.value = await res.json()
      if (currentExecution.value.execution_id) {
        await pollExecutionState(currentExecution.value.execution_id)
      }
    } catch (e) {
      console.error('Failed to run execution:', e)
    } finally {
      executionLoading.value = false
      showPlanApproval.value = false
    }
  }

  async function pollExecutionState(executionId: string) {
    let maxAttempts = 30
    while (maxAttempts > 0) {
      try {
        const res = await fetch(`/api/execution/${executionId}/state`)
        const data = await res.json()
        currentExecution.value = { ...currentExecution.value, ...data }

        if (data.status === 'completed' || data.status === 'failed' || data.status === 'interrupted') {
          const reportRes = await fetch(`/api/execution/${executionId}/report`)
          executionReport.value = await reportRes.json()
          break
        }

        await new Promise(r => setTimeout(r, 1000))
        maxAttempts--
      } catch (e) {
        console.error('Polling error:', e)
        break
      }
    }
  }

  async function runStream() {
    if (!selectedAgentGraph.value || !executionInput.value.trim()) return
    executionLoading.value = true
    try {
      const res = await fetch('/api/execution/run/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          graph_id: selectedAgentGraph.value,
          input_text: executionInput.value,
          approved: true,
        }),
      })
      const reader = res.body?.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (reader) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6))
              handleStreamEvent(event)
            } catch (e) {}
          }
        }
      }
    } catch (e) {
      console.error('Stream error:', e)
    } finally {
      executionLoading.value = false
      showPlanApproval.value = false
    }
  }

  function handleStreamEvent(event: any) {
    if (event.type === 'start') {
      currentExecution.value = { execution_id: event.execution_id, status: 'running' }
    } else if (event.type === 'update') {
      nodeStatuses.value = { ...nodeStatuses.value, ...event.data }
    } else if (event.type === 'done') {
      currentExecution.value.status = 'completed'
      pollExecutionState(event.execution_id)
    } else if (event.type === 'error') {
      currentExecution.value.status = 'failed'
      currentExecution.value.error = event.error
    }
  }

  async function interruptExecution() {
    if (!currentExecution.value.execution_id) return
    try {
      await fetch(`/api/execution/${currentExecution.value.execution_id}/interrupt`, { method: 'POST' })
      currentExecution.value.status = 'interrupted'
    } catch (e) {
      console.error('Interrupt error:', e)
    }
  }

  async function resumeExecution() {
    if (!currentExecution.value.execution_id) return
    try {
      await fetch(`/api/execution/${currentExecution.value.execution_id}/resume`, { method: 'POST' })
      currentExecution.value.status = 'running'
      pollExecutionState(currentExecution.value.execution_id)
    } catch (e) {
      console.error('Resume error:', e)
    }
  }

  // Aliases for component compatibility
  const list = agents
  const graphs = agentGraphs
  const showModal = showAgentModal
  const editingId = editingAgentId
  const form = agentForm
  const selectedGraphId = selectedAgentGraph

  function openNew() {
    openNewAgent()
  }

  function openEdit(agent: AgentDef) {
    openEditAgent(agent)
  }

  function loadGraphs() {
    loadAgentGraphs()
  }

  function deleteGraph(id: string) {
    // delegate to workflows store or handle directly
    if (!confirm('确定删除此 Agent 图?')) return
    fetch(`/api/agent-graphs/${id}`, { method: 'DELETE' }).then(() => loadAgentGraphs())
  }

  function approveExecution() {
    runWithApproval()
  }

  return {
    agents, agentGraphs, loading, selectedAgent,
    showAgentModal, editingAgentId, agentForm,
    executionPlan, currentExecution, executionLoading,
    showPlanApproval, executionInput, nodeStatuses,
    showExecutionDetail, executionReport, selectedAgentGraph,
    loadAgents, loadAgentGraphs,
    createAgent, updateAgent, deleteAgent,
    openNewAgent, openEditAgent, resetAgentForm,
    generatePlan, runWithApproval, pollExecutionState,
    runStream, interruptExecution, resumeExecution,
    // Aliases
    list, graphs, showModal, editingId, form, selectedGraphId,
    openNew, openEdit, loadGraphs, deleteGraph, approveExecution,
  }
})
