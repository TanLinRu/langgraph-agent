<script setup lang="ts">
import { onMounted } from 'vue'
import { useSopStore } from '../stores/sop'
import { useAppStore } from '../stores/app'

const sop = useSopStore()
const app = useAppStore()

onMounted(() => {
  sop.loadSopStates()
})

async function resumeSop(sopName: string) {
  if (!confirm(`恢复 SOP: ${sopName}?`)) return
  try {
    const res = await fetch(`/api/sop/state/${sopName}/resume`, { method: 'POST' })
    const data = await res.json()
    if (data.error) {
      alert(data.error)
    } else {
      alert(`已准备恢复 SOP: ${sopName}\n当前步骤: ${data.current_step}`)
      app.setActiveTab('chat')
    }
  } catch (e) {
    console.error('Failed to resume SOP:', e)
  }
}
</script>

<template>
  <div class="sop-tab">
    <div class="sop-layout">
      <div class="sop-sidebar">
        <div class="sop-sidebar-section">
          <h3>📋 SOP 状态文件</h3>
          <button class="new-btn" @click="sop.loadSopStates" style="margin-bottom:12px;">🔄 刷新</button>
          <div v-if="sop.loading" class="loading-state">加载中...</div>
          <div v-else-if="sop.sopStates.length === 0" class="empty-state">
            <p>暂无 SOP 状态文件</p>
          </div>
          <div v-else class="sop-list">
            <div v-for="s in sop.sopStates" :key="s.file" class="sop-item" :class="{ active: sop.selectedSop === s.sop }" @click="sop.loadSopDetail(s.sop)">
              <span class="sop-name">{{ s.sop }}</span>
              <span class="sop-date">{{ s.date }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="sop-main">
        <div v-if="!sop.sopDetail" class="empty-detail">
          <p>选择左侧的 SOP 状态查看详情</p>
        </div>
        <div v-else class="sop-detail-panel">
          <div class="sop-detail-header">
            <h3>{{ sop.sopDetail.sop }}</h3>
            <span class="sop-status" :class="sop.sopDetail.status">{{ sop.sopDetail.status }}</span>
          </div>
          <div class="sop-info">
            <p><strong>Task ID:</strong> {{ sop.sopDetail.task_id }}</p>
            <p><strong>开始时间:</strong> {{ sop.sopDetail.started_at }}</p>
            <p><strong>当前步骤:</strong> {{ sop.sopDetail.current_step }}</p>
          </div>
          <div class="sop-steps">
            <h4>步骤进度</h4>
            <div v-for="(info, step) in sop.sopDetail.steps" :key="step" class="step-item" :class="info.status">
              <span class="step-name">{{ step }}</span>
              <span class="step-status">{{ info.status }}</span>
            </div>
          </div>
          <div v-if="sop.sopDetail.answers && Object.keys(sop.sopDetail.answers).length > 0" class="sop-answers">
            <h4>步骤答案</h4>
            <div v-for="(ans, step) in sop.sopDetail.answers" :key="step" class="answer-item">
              <p class="answer-step"><strong>{{ step }}:</strong></p>
              <pre>{{ JSON.stringify(ans, null, 2) }}</pre>
            </div>
          </div>
          <div class="sop-actions">
            <button class="resume-btn" @click="resumeSop(sop.selectedSop!)">▶️ 恢复对话</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sop-tab {
  height: calc(100vh - 50px);
}

.sop-layout {
  display: flex;
  height: 100%;
}

.sop-sidebar {
  width: 280px;
  background: #0d1117;
  border-right: 1px solid #30363d;
  overflow-y: auto;
}

.sop-sidebar-section {
  padding: 12px;
  border-bottom: 1px solid #21262d;
}

.sop-sidebar-section h3 {
  font-size: 14px;
  color: #e1e4e8;
  margin-bottom: 12px;
}

.new-btn {
  background: #238636;
  color: #fff;
  border: none;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.loading-state {
  text-align: center;
  padding: 20px;
  color: #8b949e;
}

.empty-state {
  background: #161b22;
  border: 1px dashed #30363d;
  border-radius: 6px;
  padding: 20px;
  font-size: 13px;
  color: #8b949e;
  text-align: center;
}

.sop-list {
  max-height: 400px;
  overflow-y: auto;
}

.sop-item {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 6px;
  padding: 10px;
  margin-bottom: 8px;
  cursor: pointer;
}

.sop-item:hover,
.sop-item.active {
  border-color: #58a6ff;
}

.sop-name {
  font-size: 13px;
  font-weight: 600;
  color: #e1e4e8;
}

.sop-date {
  font-size: 11px;
  color: #8b949e;
  margin-left: 8px;
}

.sop-main {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
}

.empty-detail {
  text-align: center;
  padding: 40px;
  color: #8b949e;
}

.sop-detail-panel {
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 20px;
}

.sop-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.sop-detail-header h3 {
  font-size: 18px;
  color: #e1e4e8;
}

.sop-status {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
}

.sop-status.in_progress { background: #1f6feb; color: #fff; }
.sop-status.completed { background: #238636; color: #fff; }
.sop-status.failed { background: #da3633; color: #fff; }

.sop-info {
  margin-bottom: 20px;
}

.sop-info p {
  font-size: 13px;
  color: #c9d1d9;
  margin-bottom: 8px;
}

.sop-steps {
  margin-bottom: 20px;
}

.sop-steps h4 {
  font-size: 14px;
  color: #e1e4e8;
  margin-bottom: 12px;
}

.step-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px;
  background: #161b22;
  border-radius: 6px;
  margin-bottom: 6px;
}

.step-name {
  font-size: 13px;
  color: #c9d1d9;
}

.step-status {
  font-size: 12px;
}

.step-item.completed .step-status { color: #3fb950; }
.step-item.in_progress .step-status { color: #58a6ff; }
.step-item.pending .step-status { color: #8b949e; }

.sop-answers h4 {
  font-size: 14px;
  color: #e1e4e8;
  margin-bottom: 12px;
}

.answer-item {
  background: #161b22;
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
}

.answer-step {
  font-size: 13px;
  color: #c9d1d9;
  margin-bottom: 8px;
}

.answer-item pre {
  font-size: 11px;
  color: #8b949e;
  white-space: pre-wrap;
}

.sop-actions {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #21262d;
}

.resume-btn {
  background: #238636;
  color: #fff;
  border: none;
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.resume-btn:hover {
  background: #2ea043;
}
</style>
