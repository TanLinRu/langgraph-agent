import { defineStore } from 'pinia'
import { ref, nextTick } from 'vue'
import type { ChatTurn, Session, Message, ToolCall } from '../types'

export const useChatStore = defineStore('chat', () => {
  const inputText = ref('')
  const turns = ref<ChatTurn[]>([])
  const loading = ref(false)
  const error = ref('')
  const chatArea = ref<HTMLElement>()
  const sessions = ref<Session[]>([])
  const selectedSession = ref('')
  const sessionsLoading = ref(false)
  let turnId = 0

  function scrollToBottom() {
    if (chatArea.value) {
      chatArea.value.scrollTop = chatArea.value.scrollHeight
    }
  }

  async function loadSessions() {
    sessionsLoading.value = true
    try {
      const res = await fetch('/api/sessions')
      const data = await res.json()
      sessions.value = data.sessions || []
      if (sessions.value.length > 0 && !selectedSession.value) {
        selectedSession.value = sessions.value[0].thread_id
        await loadSession(selectedSession.value)
      }
    } catch (e) {
      console.error('Failed to load sessions:', e)
    } finally {
      sessionsLoading.value = false
    }
  }

  async function loadSession(threadId: string) {
    selectedSession.value = threadId
    try {
      const res = await fetch('/api/sessions/' + threadId)
      const data = await res.json()
      turns.value = []
      turnId = 0

      let currentTurn: ChatTurn | null = null
      let toolCalls: ToolCall[] = []
      let reply = ''

      for (const msg of data.messages || []) {
        const role = msg.role
        if (role === 'user') {
          if (currentTurn) {
            turns.value.push(currentTurn)
          }
          turnId++
          toolCalls = []
          reply = ''
          currentTurn = {
            id: turnId,
            userMessage: msg.content,
            reply: '',
            messages: [],
            tool_calls: null,
            metrics: {},
            compression_count: null,
            elapsed_sec: 0,
            expanded: false,
          }
        } else if (role === 'assistant') {
          if (!currentTurn) continue
          const content = msg.content || ''
          if (msg.tool_calls && msg.tool_calls.length > 0) {
            for (const tc of msg.tool_calls) {
              toolCalls.push({ name: tc.name, arguments: tc.args })
            }
          } else if (content) {
            reply = content
          }
          currentTurn.messages.push(msg)
        } else if (role === 'tool') {
          if (!currentTurn) continue
          currentTurn.messages.push(msg)
          for (const tc of toolCalls) {
            if (!tc.result) {
              tc.result = msg.content
              break
            }
          }
        }
      }

      if (currentTurn) {
        currentTurn.reply = reply
        currentTurn.tool_calls = toolCalls.length > 0 ? toolCalls : null
        turns.value.push(currentTurn)
      }

      await nextTick()
      scrollToBottom()
    } catch (e) {
      console.error('Failed to load session:', e)
    }
  }

  async function sendMessage() {
    const text = inputText.value.trim()
    if (!text || loading.value) return

    inputText.value = ''
    error.value = ''
    loading.value = true
    turnId++

    const threadId = selectedSession.value || 'session-' + Date.now()

    const currentTurn: ChatTurn = {
      id: turnId,
      userMessage: text,
      reply: '',
      messages: [],
      tool_calls: null,
      toolInvocations: [],
      executionSteps: [],
      executionGraph: undefined,
      metrics: {},
      compression_count: null,
      elapsed_sec: 0,
      expanded: false,
    }
    turns.value.push(currentTurn)

    await nextTick()
    scrollToBottom()

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, thread_id: threadId }),
      })
      const data = await res.json()

      if (data.status === 'error') {
        error.value = data.reply
        return
      }

      currentTurn.reply = data.reply || '(无回复)'
      currentTurn.messages = data.messages || []
      currentTurn.tool_calls = data.tool_calls
      currentTurn.metrics = data.metrics || {}
      currentTurn.compression_count = data.compression_count
      currentTurn.elapsed_sec = data.elapsed_sec

      await nextTick()
      scrollToBottom()
    } catch (e) {
      error.value = `请求失败: ${e}`
    } finally {
      loading.value = false
    }
  }

  function selectSession(threadId: string) {
    loadSession(threadId)
  }

  function newSession() {
    turns.value = []
    turnId = 0
    selectedSession.value = ''
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  function setChatArea(el: HTMLElement | undefined) {
    chatArea.value = el
  }

  return {
    inputText, turns, loading, error, chatArea,
    sessions, selectedSession, sessionsLoading,
    loadSessions, loadSession, sendMessage,
    selectSession, newSession, handleKeydown,
    scrollToBottom, setChatArea,
  }
})
