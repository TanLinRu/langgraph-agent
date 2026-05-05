<script setup lang="ts">
import { ref, computed } from 'vue'

interface PRDField {
  name: string
  label: string
  type: 'text' | 'textarea' | 'select' | 'number'
  required: boolean
  placeholder?: string
  options?: { value: string; label: string }[]
}

interface PRDSubmitData {
  project_name: string
  product_type: string
  target_users: string
  core_features: string
  user_flow: string
  data_model: string
  apiRequirements: string
  tech_constraints: string
}

const fields: PRDField[] = [
  { name: 'project_name', label: '项目名称', type: 'text', required: true, placeholder: '请输入项目名称' },
  { name: 'product_type', label: '产品类型', type: 'select', required: true, options: [
    { value: 'web', label: 'Web 应用' },
    { value: 'mobile', label: '移动端应用' },
    { value: 'desktop', label: '桌面应用' },
    { value: 'api', label: 'API 服务' },
    { value: 'mini', label: '小程序' },
  ]},
  { name: 'target_users', label: '目标用户', type: 'textarea', required: true, placeholder: '描述目标用户群体' },
  { name: 'core_features', label: '核心功能', type: 'textarea', required: true, placeholder: '列出核心功能点，每行一个' },
  { name: 'user_flow', label: '用户流程', type: 'textarea', required: false, placeholder: '描述主要用户流程' },
  { name: 'data_model', label: '数据模型', type: 'textarea', required: false, placeholder: '描述核心数据结构' },
  { name: 'apiRequirements', label: 'API 需求', type: 'textarea', required: false, placeholder: '列出需要的 API' },
  { name: 'tech_constraints', label: '技术约束', type: 'textarea', required: false, placeholder: '技术选型、依赖等' },
]

const formData = ref<Record<string, string>>({})
const submitting = ref(false)
const submitted = ref(false)
const errors = ref<Record<string, string>>({})

function initForm() {
  for (const field of fields) {
    formData.value[field.name] = ''
  }
}
initForm()

const isValid = computed(() => {
  for (const field of fields) {
    if (field.required && !formData.value[field.name]?.trim()) {
      return false
    }
  }
  return true
})

function validate(): boolean {
  errors.value = {}
  for (const field of fields) {
    if (field.required && !formData.value[field.name]?.trim()) {
      errors.value[field.name] = '必填'
    }
  }
  return Object.keys(errors.value).length === 0
}

async function submit() {
  if (!validate()) return
  
  submitting.value = true
  try {
    const response = await fetch('/api/execution/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        graph_id: 'wf-prd-design',
        input_text: formatPRDText(),
      }),
    })
    const data = await response.json()
    if (data.execution_id || data.status) {
      submitted.value = true
    }
  } catch (e) {
    console.error('PRD submission error:', e)
  } finally {
    submitting.value = false
  }
}

function formatPRDText(): string {
  let text = '# PRD 需求文档\n\n'
  for (const field of fields) {
    const value = formData.value[field.name]?.trim()
    if (value) {
      text += `## ${field.label}\n${value}\n\n`
    }
  }
  return text
}

function reset() {
  initForm()
  submitted.value = false
  errors.value = {}
}
</script>

<template>
  <div class="prd-form">
    <div class="form-header">
      <h3>PRD 可视化设计</h3>
      <p class="form-desc">填写产品需求文档，自动生成流程图和 HTML 原型</p>
    </div>

    <div v-if="!submitted" class="form-body">
      <div v-for="field in fields" :key="field.name" class="form-group">
        <label :for="field.name">
          {{ field.label }}
          <span v-if="field.required" class="required">*</span>
        </label>

        <input
          v-if="field.type === 'text'"
          :id="field.name"
          v-model="formData[field.name]"
          :placeholder="field.placeholder"
          :class="{ error: errors[field.name] }"
          type="text"
        />

        <select
          v-else-if="field.type === 'select'"
          :id="field.name"
          v-model="formData[field.name]"
          :class="{ error: errors[field.name] }"
        >
          <option value="">请选择</option>
          <option v-for="opt in field.options" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>

        <textarea
          v-else-if="field.type === 'textarea'"
          :id="field.name"
          v-model="formData[field.name]"
          :placeholder="field.placeholder"
          :class="{ error: errors[field.name] }"
          rows="3"
        ></textarea>

        <span v-if="errors[field.name]" class="error-msg">{{ errors[field.name] }}</span>
      </div>

      <div class="form-actions">
        <button class="btn-reset" @click="reset">重置</button>
        <button 
          class="btn-submit" 
          @click="submit" 
          :disabled="!isValid || submitting"
        >
          {{ submitting ? '生成中...' : '生成设计' }}
        </button>
      </div>
    </div>

    <div v-else class="form-result">
      <div class="result-header">
        <span class="result-icon">✓</span>
        <span>PRD 已提交</span>
      </div>
      <p>正在生成流程图和 HTML 原型...</p>
      <button class="btn-new" @click="reset">新建 PRD</button>
    </div>
  </div>
</template>

<style scoped>
.prd-form {
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  overflow: hidden;
}

.form-header {
  padding: 16px;
  border-bottom: 1px solid #30363d;
}

.form-header h3 {
  margin: 0 0 4px;
  font-size: 16px;
  color: #e6edf3;
}

.form-desc {
  margin: 0;
  font-size: 12px;
  color: #8b949e;
}

.form-body {
  padding: 16px;
  max-height: 400px;
  overflow-y: auto;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: #e6edf3;
}

.required {
  color: #f85149;
}

.form-group input,
.form-group select,
.form-group textarea {
  width: 100%;
  padding: 8px 12px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #e6edf3;
  font-size: 13px;
}

.form-group input:focus,
.form-group select:focus,
.form-group textarea:focus {
  outline: none;
  border-color: #58a6ff;
}

.form-group input.error,
.form-group select.error,
.form-group textarea.error {
  border-color: #f85149;
}

.form-group textarea {
  resize: vertical;
  min-height: 60px;
}

.error-msg {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: #f85149;
}

.form-actions {
  display: flex;
  gap: 12px;
  padding-top: 8px;
}

.btn-reset,
.btn-submit {
  flex: 1;
  padding: 10px 16px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-reset {
  background: #21262d;
  color: #8b949e;
}

.btn-reset:hover {
  background: #30363d;
}

.btn-submit {
  background: #238636;
  color: #fff;
}

.btn-submit:hover:not(:disabled) {
  background: #2ea043;
}

.btn-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.form-result {
  padding: 32px 16px;
  text-align: center;
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 12px;
}

.result-icon {
  width: 32px;
  height: 32px;
  line-height: 32px;
  background: #238636;
  border-radius: 50%;
  color: #fff;
  font-size: 16px;
}

.form-result p {
  color: #8b949e;
  margin-bottom: 16px;
}

.btn-new {
  padding: 10px 24px;
  background: #21262d;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #e6edf3;
  cursor: pointer;
}

.btn-new:hover {
  background: #30363d;
}
</style>