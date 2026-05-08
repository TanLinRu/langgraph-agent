import { defineStore } from 'pinia'
import { ref, onUnmounted } from 'vue'
import type { AgentActivity, SkillTrigger, TaskProgress, Observation } from '../types'
import { useOrchestratorStore } from './orchestrator'

export const useDashboardStore = defineStore('dashboard', () => {
  const isOpen = ref(true)
  const connected = ref(false)

  // Auto-connect on store creation
  if (typeof window !== 'undefined') {
    setTimeout(() => {
      if (isOpen.value && !connected.value) {
        connectSSE()
      }
    }, 500)
  }

  const agentActivities = ref<Map<string, AgentActivity>>(new Map())
  const skillTriggers = ref<SkillTrigger[]>([])
  const taskProgresses = ref<Map<string, TaskProgress>>(new Map())
  const observations = ref<Observation[]>([])
  const counters = ref<Record<string, number>>({})
  let eventSource: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let observationId = 0

  const MAX_OBSERVATIONS = 200
  const TRIM_TO = 100
  const MAX_SKILL_TRIGGERS = 50

  function toggle() {
    isOpen.value = !isOpen.value
    if (isOpen.value && !connected.value) {
      connectSSE()
    }
  }

  async function loadSnapshot() {
    try {
      const res = await fetch('/api/events/snapshot')
      const data = await res.json()
      if (data.recent_events) {
        for (const evt of data.recent_events) {
          handleEvent(evt.type, evt.data, evt.timestamp)
        }
      }
    } catch (e) {
      console.error('[Dashboard] Failed to load snapshot:', e)
    }
  }

  function connectSSE() {
    if (eventSource) return

    loadSnapshot()

    eventSource = new EventSource('/api/events/stream')
    connected.value = true

    eventSource.addEventListener('agent_status', (e) => {
      try {
        const data = JSON.parse(e.data)
        handleAgentStatus(data.data, data.timestamp)
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('skill_trigger', (e) => {
      try {
        const data = JSON.parse(e.data)
        handleSkillTrigger(data.data, data.timestamp)
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('task_progress', (e) => {
      try {
        const data = JSON.parse(e.data)
        handleTaskProgress(data.data, data.timestamp)
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('step_complete', (e) => {
      try {
        const data = JSON.parse(e.data)
        handleStepComplete(data.data, data.timestamp)
      } catch { /* ignore */ }
    })

    eventSource.addEventListener('metric_update', (e) => {
      try {
        const data = JSON.parse(e.data)
        handleMetricUpdate(data.data, data.timestamp)
      } catch { /* ignore */ }
    })

    // Orchestrator workflow events
    const orchestrator = useOrchestratorStore()
    const orchestratorEvents: Record<string, (data: any) => void> = {
      'workflow_plan': orchestrator.handleWorkflowPlan,
      'step_update': orchestrator.handleStepUpdate,
      'workflow_replan': orchestrator.handleWorkflowReplan,
      'workflow_complete': orchestrator.handleWorkflowComplete,
    }
    for (const [eventType, handler] of Object.entries(orchestratorEvents)) {
      eventSource.addEventListener(eventType, (e) => {
        try {
          const data = JSON.parse(e.data)
          handler(data.data)
        } catch { /* ignore */ }
      })
    }

    eventSource.onerror = () => {
      connected.value = false
      eventSource?.close()
      eventSource = null
      // Auto-reconnect after 3s
      reconnectTimer = setTimeout(() => {
        if (isOpen.value) connectSSE()
      }, 3000)
    }
  }

  function disconnectSSE() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    connected.value = false
  }

  function handleEvent(type: string, data: Record<string, unknown>, timestamp: string) {
    switch (type) {
      case 'agent_status': handleAgentStatus(data, timestamp); break
      case 'skill_trigger': handleSkillTrigger(data, timestamp); break
      case 'task_progress': handleTaskProgress(data, timestamp); break
      case 'step_complete': handleStepComplete(data, timestamp); break
      case 'metric_update': handleMetricUpdate(data, timestamp); break
    }
  }

  function handleMetricUpdate(data: Record<string, unknown>, timestamp: string) {
    // Update counters based on metric data
    if (data.total_tokens) {
      counters.value.total_tokens = (counters.value.total_tokens || 0) + (data.total_tokens as number)
    }
    if (data.cost_usd) {
      counters.value.total_cost_usd = (counters.value.total_cost_usd || 0) + (data.cost_usd as number)
    }
    if (data.total_llm_calls) {
      counters.value.total_llm_calls = (counters.value.total_llm_calls || 0) + 1
    }
    addObservation('metric_update', data, timestamp)
  }

  function handleAgentStatus(data: Record<string, unknown>, timestamp: string) {
    const agentId = data.agent_id as string
    const existing = agentActivities.value.get(agentId)
    const updated: AgentActivity = {
      agent_id: agentId,
      agent_name: (data.agent_name as string) || existing?.agent_name || agentId,
      status: data.status as AgentActivity['status'],
      started_at: data.status === 'running' ? timestamp : existing?.started_at,
      finished_at: data.status !== 'running' ? timestamp : undefined,
      result_summary: data.status === 'failed' ? (data.error as string) : existing?.result_summary,
    }
    agentActivities.value = new Map(agentActivities.value.set(agentId, updated))
    addObservation('agent_status', data, timestamp)
  }

  function handleSkillTrigger(data: Record<string, unknown>, timestamp: string) {
    skillTriggers.value.unshift({
      skill_name: data.tool_name as string,
      triggered_at: timestamp,
      context: data.thread_id as string,
    })
    if (skillTriggers.value.length > MAX_SKILL_TRIGGERS) {
      skillTriggers.value = skillTriggers.value.slice(0, MAX_SKILL_TRIGGERS)
    }
    addObservation('skill_trigger', data, timestamp)
  }

  function handleTaskProgress(data: Record<string, unknown>, timestamp: string) {
    const execId = data.execution_id as string
    taskProgresses.value = new Map(taskProgresses.value.set(execId, {
      execution_id: execId,
      current_step: data.current_step as number,
      total_steps: data.total_steps as number,
      status: 'running',
      started_at: timestamp,
    }))
    addObservation('task_progress', data, timestamp)
  }

  function handleStepComplete(data: Record<string, unknown>, timestamp: string) {
    addObservation('step_complete', data, timestamp)
  }

  function addObservation(eventType: string, data: Record<string, unknown>, timestamp: string) {
    observationId++
    observations.value.unshift({
      id: observationId,
      event_type: eventType,
      data,
      timestamp,
    })
    if (observations.value.length > MAX_OBSERVATIONS) {
      observations.value = observations.value.slice(0, TRIM_TO)
    }
  }

  // Cleanup on unmount
  onUnmounted(() => {
    disconnectSSE()
  })

  return {
    isOpen, connected,
    agentActivities, skillTriggers, taskProgresses, observations, counters,
    toggle, connectSSE, disconnectSSE, loadSnapshot,
  }
})
