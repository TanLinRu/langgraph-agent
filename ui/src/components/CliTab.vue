<script setup lang="ts">
import { onMounted } from 'vue'
import { useCliStore } from '../stores/cli'
import { useSkillsStore } from '../stores/skills'

const cli = useCliStore()
const skills = useSkillsStore()

onMounted(() => {
  cli.loadClis()
  cli.loadTasks()
})

function interruptStream() {
  // TODO: implement stream interruption
}
</script>

<template>
  <div class="cli-tab">
    <div class="cli-layout">
      <div class="cli-sidebar">
        <div class="cli-sidebar-section">
          <h3>🖥️ 可用 CLIs</h3>
          <div v-if="cli.available.length === 0" class="empty-clis">
            <p>未检测到可用的编码 CLI</p>
          </div>
          <div v-for="c in cli.available" :key="c.name" class="cli-item" :class="{ active: cli.selectedCli === c.name }" @click="cli.selectedCli = c.name">
            <div class="cli-item-header">
              <span class="cli-name">{{ c.name }}</span>
              <span class="cli-status" :class="{ available: c.available }">{{ c.available ? '可用' : '不可用' }}</span>
            </div>
          </div>
        </div>

        <div class="cli-sidebar-section">
          <h3>📋 任务历史</h3>
          <div v-if="cli.tasksLoading" class="loading-state">加载中...</div>
          <div v-else class="task-list">
            <div v-for="task in cli.tasks.slice(0, 10)" :key="task.id" class="task-item">
              <span class="task-cli">{{ task.cli_name }}</span>
              <span class="task-status" :class="task.result?.status">{{ task.result?.status }}</span>
              <p class="task-preview">{{ task.task.slice(0, 60) }}...</p>
            </div>
          </div>
        </div>
      </div>

      <div class="cli-main">
        <div class="dispatch-panel">
          <h3>调度任务</h3>
          <div class="dispatch-form">
            <div class="form-row">
              <div class="form-group">
                <label>CLI</label>
                <select v-model="cli.selectedCli">
                  <option v-for="c in cli.available" :key="c.name" :value="c.name">{{ c.name }}</option>
                </select>
              </div>
              <div class="form-group">
                <label>模式</label>
                <select v-model="cli.mode">
                  <option value="run">run (同步)</option>
                  <option value="serve">serve (持久)</option>
                </select>
              </div>
            </div>
            <div class="form-group">
              <label>工作目录</label>
              <input v-model="cli.workingDir" placeholder="项目根目录" />
            </div>
            <div class="form-group">
              <label>任务描述</label>
              <textarea v-model="cli.task" placeholder="详细描述需要完成的任务..." rows="4" />
            </div>
            <div class="form-row" style="align-items:center;flex-wrap:wrap;">
              <div class="form-group checkbox-group">
                <label class="switch-label">
                  <input type="checkbox" v-model="cli.autoApprove" />
                  <span class="switch-text">{{ cli.autoApprove ? '✓' : '○' }}</span>
                </label>
              </div>
              <div class="form-group" style="display:flex;align-items:center;gap:4px;">
                <label class="switch-label">
                  <input type="checkbox" v-model="cli.unlimited" />
                  <span v-if="cli.unlimited" class="switch-text" style="color:#f0883e;">∞</span>
                </label>
                <input v-if="!cli.unlimited" type="number" v-model="cli.timeout" min="10" max="36000" class="timeout-input" />
                <span v-if="!cli.unlimited" style="color:#8b949e;font-size:12px;">秒</span>
              </div>
            </div>
            <div>
              <button class="dispatch-btn" @click="cli.dispatch()" :disabled="cli.loading || cli.streamStatus === 'running'">
                {{ cli.loading || cli.streamStatus === 'running' ? '调度中...' : '⚡ 调度任务' }}
              </button>
              <button v-if="cli.streamStatus === 'running'" class="interrupt-btn" @click="interruptStream">
                ⏹ 中断
              </button>
            </div>
          </div>
        </div>

        <div v-if="cli.streamStatus" class="stream-panel" :class="cli.streamStatus">
          <div class="stream-header">
            <h3>
              <span v-if="cli.streamStatus === 'running'" class="stream-icon running">⏳</span>
              <span v-else-if="cli.streamStatus === 'success'" class="stream-icon success">✓</span>
              <span v-else class="stream-icon error">✗</span>
              {{ cli.streamStatus === 'running' ? '执行中...' : cli.streamStatus === 'success' ? '完成' : '失败' }}
            </h3>
            <span class="duration">{{ cli.streamDuration }}s</span>
          </div>
          <div class="stream-output">
            <pre>{{ cli.streamOutput }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cli-tab {
  height: calc(100vh - 50px);
}

.cli-layout {
  display: flex;
  height: 100%;
}

.cli-sidebar {
  width: 300px;
  background: #0d1117;
  border-right: 1px solid #30363d;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.cli-sidebar-section {
  padding: 12px;
  border-bottom: 1px solid #21262d;
}

.cli-sidebar-section h3 {
  font-size: 14px;
  color: #e1e4e8;
  margin-bottom: 12px;
}

.empty-clis {
  background: #161b22;
  border: 1px dashed #30363d;
  border-radius: 6px;
  padding: 12px;
  font-size: 13px;
  color: #8b949e;
}

.cli-item {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 8px;
  cursor: pointer;
}

.cli-item:hover,
.cli-item.active {
  border-color: #58a6ff;
}

.cli-item-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.cli-name {
  font-size: 13px;
  font-weight: 600;
  color: #e1e4e8;
}

.cli-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  color: #8b949e;
  background: #21262d;
}

.cli-status.available {
  color: #3fb950;
  background: #1a4a2a;
}

.task-list {
  max-height: 300px;
  overflow-y: auto;
}

.task-item {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 6px;
}

.task-cli {
  font-size: 12px;
  font-weight: 600;
  color: #58a6ff;
}

.task-status {
  font-size: 14px;
  margin-left: 8px;
}

.task-preview {
  font-size: 11px;
  color: #8b949e;
  margin-top: 4px;
}

.cli-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 20px;
  gap: 20px;
}

.dispatch-panel {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 20px;
}

.dispatch-panel h3 {
  font-size: 16px;
  color: #e1e4e8;
  margin-bottom: 16px;
}

.dispatch-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-row .form-group {
  flex: 1;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 12px;
  color: #8b949e;
  margin-bottom: 6px;
}

.form-group input,
.form-group textarea,
.form-group select {
  width: 100%;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 8px 12px;
  color: #e1e4e8;
  font-size: 14px;
  font-family: inherit;
}

.checkbox-group label.switch-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.checkbox-group input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: #238636;
}

.switch-text {
  font-size: 13px;
  color: #c9d1d9;
}

.timeout-input {
  width: 70px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 4px;
  padding: 6px 8px;
  color: #e1e4e8;
  font-size: 13px;
  text-align: center;
}

.timeout-input:focus {
  border-color: #1f6feb;
  outline: none;
}

.dispatch-btn {
  background: #238636;
  color: #fff;
  border: none;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
}

.dispatch-btn:disabled {
  background: #21262d;
  color: #6e7681;
  cursor: not-allowed;
}

.interrupt-btn {
  background: #da3633;
  color: #fff;
  border: none;
  padding: 12px 20px;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  margin-left: 8px;
}

.stream-panel {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 10px;
  overflow: hidden;
}

.stream-panel.success { border-color: #238636; }
.stream-panel.error { border-color: #da3633; }

.stream-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #21262d;
}

.stream-header h3 {
  font-size: 14px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.stream-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
}

.stream-icon.running {
  background: #1f6feb;
  color: #fff;
  animation: pulse 1.5s infinite;
}

.stream-icon.success { background: #238636; color: #fff; }
.stream-icon.error { background: #da3633; color: #fff; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.duration {
  font-size: 12px;
  color: #c9d1d9;
  font-family: monospace;
}

.stream-output {
  padding: 16px;
  max-height: 400px;
  overflow-y: auto;
}

.stream-output pre {
  font-size: 12px;
  line-height: 1.5;
  color: #8b949e;
  white-space: pre-wrap;
  margin: 0;
}

.loading-state {
  text-align: center;
  padding: 20px;
  color: #8b949e;
}
</style>
