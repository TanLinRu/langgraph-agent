<script setup lang="ts">
import { useWorkflowsStore } from '../stores/workflows'

const workflows = useWorkflowsStore()
</script>

<template>
  <transition name="fade">
    <div v-if="workflows.showModal" class="modal-overlay" @click.self="workflows.showModal = false">
      <div class="modal">
        <div class="modal-header">
          <h3>
            {{ workflows.graphMode === 'workflows'
              ? (workflows.editingId ? '编辑工作流' : '新建工作流')
              : (workflows.editingGraphId ? '编辑 Agent 图' : '新建 Agent 图') }}
          </h3>
          <button class="close-btn" @click="workflows.showModal = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>名称</label>
            <input v-model="workflows.formName" placeholder="输入名称" />
          </div>
          <div class="form-group">
            <label>描述</label>
            <textarea v-model="workflows.formDescription" placeholder="输入描述" rows="2" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="workflows.showModal = false">取消</button>
          <button class="btn-primary" @click="workflows.graphMode === 'workflows' ? workflows.save() : workflows.saveAgentGraph()">
            保存
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
.form-group textarea {
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
