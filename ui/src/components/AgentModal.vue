<script setup lang="ts">
import { useAgentsStore } from '../stores/agents'

const agents = useAgentsStore()
</script>

<template>
  <transition name="fade">
    <div v-if="agents.showModal" class="modal-overlay" @click.self="agents.showModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>{{ agents.editingId ? '编辑 Agent' : '新建 Agent' }}</h3>
          <button class="close-btn" @click="agents.showModal = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>名称</label>
            <input v-model="agents.form.name" placeholder="Agent 名称" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="agents.form.description" placeholder="Agent 描述" rows="2" />
          </div>
          <div class="form-group">
            <label>LLM 模型</label>
            <select v-model="agents.form.llm_model">
              <option value="openai:gpt-4">GPT-4</option>
              <option value="openai:gpt-4o">GPT-4o</option>
              <option value="openai:gpt-4o-mini">GPT-4o-mini</option>
            </select>
          </div>
          <div class="form-group">
            <label>System Prompt</label>
            <textarea v-model="agents.form.system_prompt" placeholder="Agent 系统提示词" rows="4" />
          </div>
          <div class="form-group">
            <label>执行模式</label>
            <select v-model="agents.form.execution_mode">
              <option value="sync">同步 (Sync)</option>
              <option value="async">异步 (Async)</option>
            </select>
          </div>
          <div class="form-group">
            <label>超时时间 (秒)</label>
            <input type="number" v-model.number="agents.form.timeout" min="10" max="3600" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="agents.showModal = false">取消</button>
          <button class="btn-primary" @click="agents.editingId ? agents.updateAgent() : agents.createAgent()">
            {{ agents.editingId ? '更新' : '创建' }}
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  width: 400px;
  max-width: 90%;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #30363d;
}

.modal-body {
  padding: 20px;
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
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  padding: 8px 12px;
  color: #e1e4e8;
  font-size: 14px;
  font-family: inherit;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 20px;
  border-top: 1px solid #30363d;
}

.close-btn {
  background: none;
  border: none;
  color: #8b949e;
  font-size: 24px;
  cursor: pointer;
  line-height: 1;
}

.btn-secondary {
  background: #21262d;
  border: 1px solid #30363d;
  color: #c9d1d9;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.btn-primary {
  background: #238636;
  border: none;
  color: #fff;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
