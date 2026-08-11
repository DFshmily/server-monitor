import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useServersStore = defineStore('servers', () => {
  const servers = ref({})
  const connected = ref(false)
  const kioskMode = ref(false)
  let ws = null
  let reconnectTimer = null
  let heartbeatTimer = null
  let reconnectAttempts = 0
  const MAX_RECONNECT_DELAY = 30000   // cap at 30s
  const HEARTBEAT_INTERVAL = 25000    // ping every 25s

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

  // 带 token 的请求头(详情页/管理页需要登录)
  function authHeaders() {
    const token = localStorage.getItem('monitor_token')
    return token ? { Authorization: `Bearer ${token}` } : {}
  }

  async function saveAlias(name, alias) {
    try {
      const res = await fetch(`/api/servers/${name}/alias`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
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
      const res = await fetch(`/api/servers/${name}/latest`, { headers: authHeaders() })
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
      const res = await fetch(url, { headers: authHeaders() })
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
      reconnectAttempts = 0
      console.log('WebSocket connected')
      // Heartbeat: keep the connection alive through proxies/NAT
      clearInterval(heartbeatTimer)
      heartbeatTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send('ping')
        }
      }, HEARTBEAT_INTERVAL)
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
      clearInterval(heartbeatTimer)
      console.log('WebSocket disconnected, reconnecting...')
      scheduleReconnect()
    }

    ws.onerror = (err) => {
      console.error('WebSocket error:', err)
      ws?.close()
    }
  }

  // Exponential backoff: 3s → 6s → 12s → 24s → capped at 30s
  function scheduleReconnect() {
    clearTimeout(reconnectTimer)
    const delay = Math.min(3000 * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY)
    reconnectAttempts += 1
    reconnectTimer = setTimeout(() => {
      // Guard: if a connection attempt is already in flight, skip
      if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
      connectWebSocket()
    }, delay)
  }

  function disconnectWebSocket() {
    clearTimeout(reconnectTimer)
    clearInterval(heartbeatTimer)
    if (ws) {
      ws.onclose = null // suppress auto-reconnect during manual teardown
      ws.close()
      ws = null
    }
    connected.value = false
  }

  function enterKioskMode() {
    kioskMode.value = true
    document.documentElement.requestFullscreen?.().catch(() => {})
  }

  function exitKioskMode() {
    kioskMode.value = false
    if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {})
    }
  }

  function toggleKioskMode() {
    if (kioskMode.value) exitKioskMode()
    else enterKioskMode()
  }

  return {
    servers,
    connected,
    kioskMode,
    serverList,
    getServer,
    fetchServers,
    fetchLatest,
    fetchHistory,
    saveAlias,
    connectWebSocket,
    disconnectWebSocket,
    enterKioskMode,
    exitKioskMode,
    toggleKioskMode
  }
})
