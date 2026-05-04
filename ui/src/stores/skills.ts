import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Skill } from '../types'

export const useSkillsStore = defineStore('skills', () => {
  const skills = ref<Skill[]>([])
  const selectedSkill = ref<Skill | null>(null)
  const loading = ref(false)

  async function loadSkills() {
    loading.value = true
    try {
      const res = await fetch('/api/skills')
      const data = await res.json()
      skills.value = data.skills || []
    } catch (e) {
      console.error('Failed to load skills:', e)
    } finally {
      loading.value = false
    }
  }

  async function loadSkillDetail(name: string) {
    try {
      const res = await fetch(`/api/skills/${name}`)
      const data = await res.json()
      selectedSkill.value = data
    } catch (e) {
      console.error('Failed to load skill detail:', e)
    }
  }

  function clearSelection() {
    selectedSkill.value = null
  }

  return { skills, selectedSkill, loading, loadSkills, loadSkillDetail, clearSelection }
})
