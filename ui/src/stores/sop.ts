import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SOPStateInfo, SOPStateDetail } from '../types'

export const useSopStore = defineStore('sop', () => {
  const sopStates = ref<SOPStateInfo[]>([])
  const selectedSop = ref('')
  const sopDetail = ref<SOPStateDetail | null>(null)
  const loading = ref(false)

  async function loadSopStates() {
    loading.value = true
    try {
      const res = await fetch('/api/sop/state')
      const data = await res.json()
      sopStates.value = data.states || []
    } catch (e) {
      console.error('Failed to load SOP states:', e)
    } finally {
      loading.value = false
    }
  }

  async function loadSopDetail(sopName: string) {
    selectedSop.value = sopName
    loading.value = true
    try {
      const res = await fetch(`/api/sop/state/${sopName}`)
      const data = await res.json()
      sopDetail.value = data.state || null
    } catch (e) {
      console.error('Failed to load SOP detail:', e)
    } finally {
      loading.value = false
    }
  }

  async function resumeSop(sopName: string): Promise<number | null> {
    if (!confirm(`恢复 SOP: ${sopName}?`)) return null
    try {
      const res = await fetch(`/api/sop/state/${sopName}/resume`, { method: 'POST' })
      const data = await res.json()
      if (data.error) {
        alert(data.error)
        return null
      }
      alert(`已准备恢复 SOP: ${sopName}\n当前步骤: ${data.current_step}`)
      return data.current_step
    } catch (e) {
      console.error('Failed to resume SOP:', e)
      return null
    }
  }

  async function deleteSop(sopName: string) {
    if (!confirm(`确定删除 SOP 状态: ${sopName}?`)) return
    try {
      await fetch(`/api/sop/state/${sopName}`, { method: 'DELETE' })
      await loadSopStates()
    } catch (e) {
      console.error('Failed to delete SOP:', e)
    }
  }

  return { sopStates, selectedSop, sopDetail, loading, loadSopStates, loadSopDetail, resumeSop, deleteSop }
})
