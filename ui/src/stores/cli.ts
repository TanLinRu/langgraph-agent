import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { CliInfo, CliTask, StreamStep, StreamParsedResult } from '../types'

export const useCliStore = defineStore('cli', () => {
  const availableClis = ref<CliInfo[]>([])
  const cliTasks = ref<CliTask[]>([])
  const loading = ref(false)
  const tasksLoading = ref(false)

  // Dispatch form
  const dispatchTask = ref('')
  const dispatchCli = ref('opencode')
  const dispatchDir = ref('.')
  const dispatchMode = ref('run')
  const dispatchAutoApprove = ref(true)
  const dispatchUnlimited = ref(false)
  const dispatchTimeout = ref(600)

  // Streaming state
  const streamOutput = ref('')
  const streamStatus = ref('')
  const streamDuration = ref(0)
  const streamStartTime = ref(0)
  const streamParsed = ref<StreamParsedResult | null>(null)
  const expandedSteps = ref<Set<number>>(new Set())

  async function loadClis() {
    try {
      const res = await fetch('/api/cli')
      const data = await res.json()
      availableClis.value = data.clis || []
    } catch (e) {
      console.error('Failed to load CLIs:', e)
    }
  }

  async function loadCliTasks() {
    tasksLoading.value = true
    try {
      const res = await fetch('/api/cli/tasks')
      const data = await res.json()
      cliTasks.value = data.tasks || []
    } catch (e) {
      console.error('Failed to load CLI tasks:', e)
    } finally {
      tasksLoading.value = false
    }
  }

  function toggleStep(stepId: number) {
    const s = expandedSteps.value
    if (s.has(stepId)) s.delete(stepId)
    else s.add(stepId)
    expandedSteps.value = new Set(s)
  }

  function interruptStream() {
    // TODO: implement stream interruption
  }

  async function dispatchCliTask() {
    if (!dispatchTask.value.trim()) {
      alert('请输入任务描述')
      return
    }
    loading.value = true
    streamOutput.value = ''
    streamStatus.value = 'running'
    streamDuration.value = 0
    streamStartTime.value = Date.now()
    streamParsed.value = null

    try {
      const res = await fetch('/api/cli/dispatch/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cli_name: dispatchCli.value,
          task: dispatchTask.value,
          working_dir: dispatchDir.value,
          mode: dispatchMode.value,
          auto_approve: dispatchAutoApprove.value,
          timeout: dispatchUnlimited.value ? 0 : dispatchTimeout.value,
        }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => null)
        streamStatus.value = 'error'
        streamOutput.value += '\n调度失败: ' + (errData?.detail || res.statusText) + '\n'
        loading.value = false
        return
      }

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let stepCounter = 0
      let currentStep: StreamStep | null = null
      const steps: StreamStep[] = []
      let totalTokens = 0
      let receivedComplete = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        let currentEvent = ''
        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            try {
              const eventData = JSON.parse(line.slice(5))
              const data = eventData.data !== undefined ? eventData.data : eventData

              if (currentEvent === 'start') {
                streamOutput.value += '>>> 任务开始\n'
                streamOutput.value += 'CLI: ' + dispatchCli.value + '\n'
                streamOutput.value += '超时: ' + (data.timeout || '无限制') + 's\n\n'
              } else if (currentEvent === 'stdout') {
                streamOutput.value += JSON.stringify(data) + '\n'
                try {
                  const evt = data
                  const type = evt.type || evt.part?.type
                  const part = evt.part || {}

                  if (type === 'step_start') {
                    stepCounter++
                    currentStep = { id: stepCounter, text: '', toolCalls: [], isComplete: false }
                  } else if (type === 'text') {
                    if (!currentStep) {
                      stepCounter++
                      currentStep = { id: stepCounter, text: '', toolCalls: [], isComplete: false }
                    }
                    if (part.text) currentStep.text += part.text
                  } else if (type === 'tool_use') {
                    if (!currentStep) {
                      stepCounter++
                      currentStep = { id: stepCounter, text: '', toolCalls: [], isComplete: false }
                    }
                    currentStep.toolCalls.push({
                      tool: part.tool || 'unknown',
                      input: part.state?.input || {},
                      output: part.state?.output || '',
                      title: part.title,
                    })
                  } else if (type === 'step_finish') {
                    if (currentStep) {
                      currentStep.isComplete = true
                      currentStep.tokens = part.tokens
                      if (part.tokens) totalTokens += part.tokens.total || 0
                      steps.push({ ...currentStep })
                      currentStep = null
                    }
                  }
                } catch { /* ignore parse errors */ }
              } else if (currentEvent === 'complete') {
                receivedComplete = true
                streamStatus.value = data.status
                streamDuration.value = data.duration_sec
              } else if (currentEvent === 'error') {
                receivedComplete = true
                streamStatus.value = data.status
              }
            } catch { /* ignore parse errors */ }
          }
        }
      }

      if (!receivedComplete) {
        streamStatus.value = steps.length > 0 ? 'success' : 'error'
      }

      streamDuration.value = Math.round((Date.now() - streamStartTime.value) / 1000 * 100) / 100
      streamOutput.value += '\n状态: ' + streamStatus.value + '\n'
      streamOutput.value += '耗时: ' + streamDuration.value + 's\n'

      let finalText = ''
      for (let i = steps.length - 1; i >= 0; i--) {
        if (steps[i].text.trim()) {
          finalText = steps[i].text.trim()
          break
        }
      }

      streamParsed.value = { steps, finalText, totalTokens, totalCost: 0 }
      dispatchTask.value = ''
      await loadCliTasks()
    } catch (e) {
      console.error('Failed to dispatch task:', e)
      streamStatus.value = 'error'
      streamOutput.value += '\n调度失败: ' + e + '\n'
    } finally {
      loading.value = false
    }
  }

  // Aliases for component compatibility
  const available = availableClis
  const tasks = cliTasks
  const selectedCli = dispatchCli
  const task = dispatchTask
  const workingDir = dispatchDir
  const mode = dispatchMode
  const autoApprove = dispatchAutoApprove
  const unlimited = dispatchUnlimited
  const timeout = dispatchTimeout

  function loadTasks() {
    loadCliTasks()
  }

  function dispatch() {
    dispatchCliTask()
  }

  return {
    availableClis, cliTasks, loading, tasksLoading,
    dispatchTask, dispatchCli, dispatchDir, dispatchMode,
    dispatchAutoApprove, dispatchUnlimited, dispatchTimeout,
    streamOutput, streamStatus, streamDuration, streamStartTime,
    streamParsed, expandedSteps,
    loadClis, loadCliTasks, toggleStep, interruptStream, dispatchCliTask,
    // Aliases
    available, tasks, selectedCli, task, workingDir, mode,
    autoApprove, unlimited, timeout, loadTasks, dispatch,
  }
})
