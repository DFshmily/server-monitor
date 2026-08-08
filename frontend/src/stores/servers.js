import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useServersStore = defineStore('servers', () => {
  const servers = ref({})
  const connected = ref(false)
  let ws = null
  let reconnectTimer = null

  const serverList = computed(() => {
    return Object.values(servers.value)
  })

  const getServer = (name) => {
    return servers.value[name] || null
  }

  async function fetchServers() {
    try {
      const res = await fetch('/api/servers')
      const data = await res.json()
      // API returns [{name, alias}] objects
      for (const item of data) {
        const name = item.name
        if (!servers.value[name]) {
          servers.value[name] = {
            name,
            alias: item.alias || null,
            latest: null,
            history: []
          }
        } else {
          servers.value[name].alias = item.alias || null
        }
        // Fetch latest for each server
        fetchLatest(name)
      }
    } catch (err) {
      console.error('Failed to fetch servers:', err)
    }
  }

  async function saveAlias(name, alias) {
    try {
      const res = await fetch(`/api/servers/${name}/alias`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ alias })
      })
      if (res.ok) {
        const data = await res.json()
        if (servers.value[name]) {
          servers.value[name].alias = data.alias
        }
        return true
      }
      return false
    } catch (err) {
      console.error(`Failed to save alias for ${name}:`, err)
      return false
    }
  }

  async function fetchLatest(name) {
    try {
      const res = await fetch(`/api/servers/${name}/latest`)
      const data = await res.json()
      if (servers.value[name]) {
        servers.value[name].latest = data
      } else {
        servers.value[name] = { name, latest: data, history: [] }
      }
      return data
    } catch (err) {
      console.error(`Failed to fetch latest for ${name}:`, err)
      return null
    }
  }

  async function fetchHistory(name, interval = '1min', limit = 100, start = null, end = null) {
    try {
      let url = `/api/servers/${name}/history?interval=${interval}&limit=${limit}`
      if (start) url += `&start=${start}`
      if (end) url += `&end=${end}`
      const res = await fetch(url)
      const data = await res.json()
      if (servers.value[name]) {
        servers.value[name].history = data
      }
      return data
    } catch (err) {
      console.error(`Failed to fetch history for ${name}:`, err)
      return []
    }
  }

  function connectWebSocket() {
    if (ws && ws.readyState === WebSocket.OPEN) return

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${location.host}/ws`

    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      connected.value = true
      console.log('WebSocket connected')
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        // Backend sends: { type: "metrics", server_name: "oracle", data: {...} }
        if (msg.type === 'metrics' && msg.server_name) {
          const name = msg.server_name
          if (!servers.value[name]) {
            servers.value[name] = { name, latest: null, history: [] }
          }
          servers.value[name].latest = msg.data
        }
      } catch (err) {
        console.error('Failed to parse WS message:', err)
      }
    }

    ws.onclose = () => {
      connected.value = false
      console.log('WebSocket disconnected, reconnecting...')
      clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(connectWebSocket, 3000)
    }

    ws.onerror = (err) => {
      console.error('WebSocket error:', err)
      ws.close()
    }
  }

  function disconnectWebSocket() {
    clearTimeout(reconnectTimer)
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
  }

  return {
    servers,
    connected,
    serverList,
    getServer,
    fetchServers,
    fetchLatest,
    fetchHistory,
    saveAlias,
    connectWebSocket,
    disconnectWebSocket
  }
})
