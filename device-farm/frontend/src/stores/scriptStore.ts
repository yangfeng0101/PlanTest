import { create } from 'zustand'
import type { Script } from '@/types'

interface ScriptState {
  scripts: Script[]
  currentScript: Script | null
  loading: boolean
  fetchScripts: () => Promise<void>
  setCurrentScript: (script: Script | null) => void
  createScript: (script: Omit<Script, 'id' | 'createdAt' | 'updatedAt'>) => Promise<void>
  updateScript: (id: string, script: Partial<Script>) => Promise<void>
  deleteScript: (id: string) => Promise<void>
}

export const useScriptStore = create<ScriptState>((set, get) => ({
  scripts: [],
  currentScript: null,
  loading: false,

  fetchScripts: async () => {
    set({ loading: true })
    try {
      const data = await fetch('/api/v1/scripts').then((res) => res.json())
      set({ scripts: data || [], loading: false })
    } catch (error) {
      console.error('Failed to fetch scripts:', error)
      set({ loading: false })
    }
  },

  setCurrentScript: (script) => set({ currentScript: script }),

  createScript: async (script) => {
    try {
      await fetch('/api/v1/scripts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(script),
      })
      const { fetchScripts } = get()
      await fetchScripts()
    } catch (error) {
      console.error('Failed to create script:', error)
    }
  },

  updateScript: async (id, script) => {
    try {
      await fetch(`/api/v1/scripts/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(script),
      })
      const { fetchScripts } = get()
      await fetchScripts()
    } catch (error) {
      console.error('Failed to update script:', error)
    }
  },

  deleteScript: async (id) => {
    try {
      await fetch(`/api/v1/scripts/${id}`, { method: 'DELETE' })
      const { fetchScripts } = get()
      await fetchScripts()
    } catch (error) {
      console.error('Failed to delete script:', error)
    }
  },
}))
