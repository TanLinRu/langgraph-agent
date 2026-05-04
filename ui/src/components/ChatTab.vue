<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { useChatStore } from '../stores/chat'
import { useDashboardStore } from '../stores/dashboard'
import { formatTime, truncate } from '../utils/format'
import DashboardSidebar from './dashboard/DashboardSidebar.vue'

const chat = useChatStore()
const dashboard = useDashboardStore()
const chatArea = ref<HTMLElement>()

function scrollToBottom() {
  if (chatArea.value) {
    chatArea.value.scrollTop = chatArea.value.scrollHeight
  }
}

async function sendMessage() {
  const text = chat.inputText.trim()
  if (!text || chat.loading) return

  chat.inputText = ''
  chat.error = ''

  // Use store's sendMessage but with our scroll behavior
  const threadId = chat.selectedSession || 'session-' + Date.now()

  // We need to do the turn creation and scroll manually since store doesn't have chatArea ref
  chat.loading = true
  const turnId = Date.now()
  const currentTurn = {
    id: turnId,
    userMessage: text,
    reply: '',
    messages: [] as any[],
    tool_calls: null as any,
    metrics: {} as Record<string, unknown>,
    compression_count: null as number | null,
    elapsed_sec: 0,
    expanded: false,
  }
  chat.turns.push(currentTurn)

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
      chat.error = data.reply
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
    chat.error = `请求失败: ${e}`
  } finally {
    chat.loading = false
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function selectSession(threadId: string) {
  await chat.loadSession(threadId)
  await nextTick()
  scrollToBottom()
}

function newSession() {
  chat.turns = []
  chat.selectedSession = ''
}

onMounted(() => {
  dashboard.connectSSE()
  chat.loadSessions()
})
</script>

<template>
  <div class="chat-tab">
    <div class="chat-layout">
      <div class="session-sidebar">
        <div class="sidebar-header">
          <h3>历史会话</h3>
          <button class="new-session-btn" @click="newSession" title="新会话">+</button>
        </div>
        <div v-if="chat.sessionsLoading" class="sidebar-loading">加载中...</div>
        <div v-else class="session-list">
          <div
            v-for="session in chat.sessions"
            :key="session.thread_id"
            :class="['session-item', { active: chat.selectedSession === session.thread_id }]"
            @click="selectSession(session.thread_id)"
          >
            <div class="session-preview">{{ session.preview || '空会话' }}</div>
            <div class="session-meta">
              <span class="session-time">{{ formatTime(session.updated_at) }}</span>
              <span class="session-id">{{ session.thread_id.slice(0, 8) }}...</span>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-main">
        <div ref="chatArea" class="chat-area">
          <template v-if="chat.turns.length === 0 && !chat.loading">
            <div class="empty-state">
              <div class="empty-icon">💬</div>
              <p>输入消息开始与 Agent 对话</p>
              <p class="hint">支持多轮对话，每轮回复可展开查看完整请求信息</p>
            </div>
          </template>

          <div v-for="turn in chat.turns" :key="turn.id" class="turn-block">
            <div class="msg-row msg-user">
              <div class="msg-avatar user-avatar">U</div>
              <div class="msg-bubble user-bubble">
                <div class="msg-text">{{ turn.userMessage }}</div>
              </div>
            </div>

            <div class="msg-row msg-assistant">
              <div class="msg-avatar agent-avatar">A</div>
              <div class="msg-bubble agent-bubble">
                <div class="msg-text">{{ turn.reply }}</div>
              </div>
            </div>

            <div class="metrics-bar">
              <span class="metric" v-if="turn.metrics.total_tokens">
                <span class="metric-label">Token</span>
                <span class="metric-value">{{ turn.metrics.total_tokens }}</span>
              </span>
              <span class="metric" v-if="turn.tool_calls?.length">
                <span class="metric-label">工具</span>
                <span class="metric-value">{{ turn.tool_calls.length }}</span>
              </span>
              <span class="metric">
                <span class="metric-label">耗时</span>
                <span class="metric-value">{{ turn.elapsed_sec }}s</span>
              </span>
              <button class="detail-btn" @click="turn.expanded = !turn.expanded">
                {{ turn.expanded ? '▲ 收起' : '▼ 详情' }}
              </button>
            </div>

            <transition name="slide">
              <div v-if="turn.expanded" class="detail-panel">
                <h4>消息序列 ({{ turn.messages.length }})</h4>
                <div v-for="(msg, mi) in turn.messages" :key="mi" class="detail-row">
                  <div class="detail-header">
                    <span :class="['role-tag', `role-${msg.role}`]">{{ msg.role }}</span>
                  </div>
                  <pre class="msg-content">{{ truncate(msg.content, 800) }}</pre>
                  <div v-if="msg.tool_calls && msg.tool_calls.length > 0" class="tool-calls">
                    <div v-for="(tc, ti) in msg.tool_calls" :key="ti" class="tool-call-item">
                      <span class="tc-name">{{ tc.name }}</span>
                      <pre class="tc-args">{{ typeof tc.arguments === 'string' ? tc.arguments : JSON.stringify(tc.arguments, null, 2) }}</pre>
                    </div>
                  </div>
                </div>
              </div>
            </transition>
          </div>

          <div v-if="chat.loading" class="msg-row msg-assistant">
            <div class="msg-avatar agent-avatar">A</div>
            <div class="msg-bubble agent-bubble loading">
              <div class="loading-dots">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>

          <div v-if="chat.error" class="error-msg">{{ chat.error }}</div>
        </div>

        <div class="input-area">
          <textarea
            v-model="chat.inputText"
            @keydown="handleKeydown"
            placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
            :disabled="chat.loading"
            rows="2"
          />
          <button class="send-btn" @click="sendMessage" :disabled="chat.loading || !chat.inputText.trim()">
            发送
          </button>
        </div>
      </div>

      <DashboardSidebar />
    </div>
  </div>
</template>

<style scoped>
.chat-tab {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 50px);
}

.chat-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.session-sidebar {
  width: 260px;
  background: #0d1117;
  border-right: 1px solid #30363d;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #30363d;
}

.sidebar-header h3 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}

.new-session-btn {
  background: #238636;
  color: white;
  border: none;
  border-radius: 6px;
  width: 28px;
  height: 28px;
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.session-list {
  flex: 1;
  overflow-y: auto;
}

.session-item {
  padding: 12px 16px;
  border-bottom: 1px solid #21262d;
  cursor: pointer;
}

.session-item:hover {
  background: #161b22;
}

.session-item.active {
  background: #1f2937;
  border-left: 3px solid #58a6ff;
}

.session-preview {
  font-size: 13px;
  color: #c9d1d9;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.session-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #6e7681;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: #8b949e;
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.turn-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.msg-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  max-width: 85%;
}

.msg-user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.msg-assistant {
  align-self: flex-start;
}

.msg-avatar {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.user-avatar {
  background: #238636;
  color: #fff;
}

.agent-avatar {
  background: #1f6feb;
  color: #fff;
}

.msg-bubble {
  padding: 10px 14px;
  border-radius: 10px;
  max-width: 100%;
}

.user-bubble {
  background: #238636;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.agent-bubble {
  background: #21262d;
  border: 1px solid #30363d;
  border-bottom-left-radius: 4px;
}

.msg-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
  font-size: 14px;
}

.metrics-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  padding-left: 38px;
  flex-wrap: wrap;
  color: #8b949e;
}

.metric {
  display: flex;
  gap: 4px;
}

.metric-label {
  color: #6e7681;
}

.metric-value {
  color: #c9d1d9;
  font-family: 'SF Mono', monospace;
  font-weight: 500;
}

.detail-btn {
  margin-left: auto;
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 4px;
  padding: 2px 10px;
  font-size: 12px;
  color: #8b949e;
  cursor: pointer;
}

.detail-panel {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 14px;
  margin-left: 38px;
  max-width: 95%;
}

.detail-panel h4 {
  font-size: 13px;
  color: #8b949e;
  margin: 14px 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.detail-row {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 8px;
}

.role-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.role-system { background: #1a3a5c; color: #58a6ff; }
.role-user { background: #1a4a2a; color: #3fb950; }
.role-assistant { background: #3a2a0a; color: #d29922; }
.role-tool { background: #3a1a3a; color: #bc8cff; }

.msg-content {
  font-size: 12px;
  white-space: pre-wrap;
  background: #0d1117;
  padding: 8px;
  border-radius: 4px;
  color: #c9d1d9;
  font-family: monospace;
}

.input-area {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: #0d1117;
  border-top: 1px solid #30363d;
}

.input-area textarea {
  flex: 1;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 14px;
  resize: none;
  font-family: inherit;
  color: #c9d1d9;
}

.input-area textarea:focus {
  outline: none;
  border-color: #58a6ff;
}

.send-btn {
  background: #238636;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 0 20px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.send-btn:disabled {
  background: #21262d;
  color: #6e7681;
  cursor: not-allowed;
}

.loading-dots {
  display: flex;
  gap: 4px;
}

.loading-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #8b949e;
  animation: dot-pulse 1.4s infinite;
}

.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes dot-pulse {
  0%, 80%, 100% { opacity: 0.3; }
  40% { opacity: 1; }
}

.error-msg {
  background: #da363322;
  border: 1px solid #da3633;
  border-radius: 8px;
  padding: 10px 14px;
  color: #f85149;
  font-size: 13px;
}

.tc-name {
  font-size: 12px;
  font-weight: 600;
  color: #58a6ff;
}

.tc-args {
  font-size: 11px;
  color: #8b949e;
  white-space: pre-wrap;
  margin: 4px 0 0;
  background: #0d1117;
  padding: 6px;
  border-radius: 4px;
}

.slide-enter-active, .slide-leave-active { transition: all 0.2s; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(-8px); }

.sidebar-loading {
  padding: 20px;
  text-align: center;
  color: #8b949e;
  font-size: 13px;
}
</style>
