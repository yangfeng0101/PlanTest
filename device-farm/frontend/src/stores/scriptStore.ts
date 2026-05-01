import { create } from 'zustand'
import type { Script } from '@/types'
import { scriptApi } from '@/services/api'

interface ScriptState {
  scripts: Script[]
  currentScript: Script | null
  loading: boolean
  fetchScripts: () => Promise<void>
  setCurrentScript: (script: Script | null) => void
  createScript: (script: Omit<Script, 'id' | 'created_at' | 'updated_at'>) => Promise<void>
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
      const response = await scriptApi.getList()
      set({ scripts: response.data.items || [], loading: false })
    } catch (error) {
      console.error('Failed to fetch scripts:', error)
      set({ loading: false })
    }
  },

  setCurrentScript: (script) => set({ currentScript: script }),

  createScript: async (script) => {
    try {
      await scriptApi.create(script)
      const { fetchScripts } = get()
      await fetchScripts()
    } catch (error) {
      console.error('Failed to create script:', error)
    }
  },

  updateScript: async (id, script) => {
    try {
      await scriptApi.update(id, script)
      const { fetchScripts } = get()
      await fetchScripts()
    } catch (error) {
      console.error('Failed to update script:', error)
    }
  },

  deleteScript: async (id) => {
    try {
      await scriptApi.delete(id)
      const { fetchScripts } = get()
      await fetchScripts()
    } catch (error) {
      console.error('Failed to delete script:', error)
    }
  },
}))
