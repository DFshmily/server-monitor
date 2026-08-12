<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import AlertStatsChart from '../components/AlertStatsChart.vue'
import TrafficDailyChart from '../components/TrafficDailyChart.vue'

const router = useRouter()
const auth = useAuthStore()

const ROOT_EMAIL = 'admin@dfshmily.icu'
const isRoot = computed(() => auth.user?.email === ROOT_EMAIL)

const users = ref([])
const invites = ref([])
const error = ref('')
const success = ref('')
const loading = ref(false)
const showInvites = ref(false)
const inviteCount = ref(5)          // 自定义生成数量
const inviteDays = ref(7)           // 自动生成有效期(天)
const newCodes = ref([])            // 本次新生成的码(高亮)
const manualCode = ref('')          // 手动添加的邀请码
const manualDays = ref(7)           // 手动邀请码有效期(天)
const confirmTarget = ref(null)     // 待确认取消的邀请码(非null时显示确认弹窗)
const showManual = ref(false)       // 自定义邀请码输入区是否展开

const newPass = ref('')
const confirmPass = ref('')
const showChangePass = ref(false)

// ── 告警规则 ──
const rules = ref([])
const events = ref([])
const audits = ref([])
const ruleForm = ref({ server_name: '*', metric: 'cpu', operator: '>', threshold: 80, enabled: true })
const METRIC_OPTIONS = [
  { value: 'cpu', label: 'CPU 使用率 %' },
  { value: 'memory', label: '内存使用率 %' },
  { value: 'disk', label: '磁盘使用率 %' },
  { value: 'load1', label: '负载 1 分钟' },
  { value: 'load5', label: '负载 5 分钟' },
  { value: 'load15', label: '负载 15 分钟' },
  { value: 'net_in', label: '网络入速率 B/s' },
  { value: 'net_out', label: '网络出速率 B/s' },
  { value: 'cert_days', label: 'SSL 证书剩余天数' },
  { value: 'traffic_month_total_gb', label: '本月流量合计 GB' },
  { value: 'traffic_used_percent', label: '本月流量额度使用 %' }
]
const OP_OPTIONS = ['>', '>=', '<', '<=']
const testNotifying = ref(false)
const testResult = ref('')

async function testNotify() {
  testNotifying.value = true
  testResult.value = ''
  error.value = ''
  try {
    const res = await api('/api/alerts/test', { method: 'POST' })
    if (res.sent && res.sent.length > 0) {
      const parts = res.sent.map(c => CHANNEL_NAMES[c] || c)
      testResult.value = `✅ 已发送到 ${parts.join(' + ')}${res.failed?.length ? `（失败: ${res.failed.join(', ')}）` : ''}`
    } else {
      testResult.value = res.message || '未配置通知渠道'
    }
  } catch (e) {
    error.value = e.message
  } finally {
    testNotifying.value = false
  }
}

async function loadRules() {
  try {
    rules.value = await api('/api/alerts/rules')
  } catch (e) { error.value = e.message }
}
const servers = ref([])
async function loadServers() {
  try {
    servers.value = await api('/api/servers')
    // 顺带取最新数据, 用于月度汇总行
    for (const s of servers.value) {
      try { s.latest = await api(`/api/servers/${s.name}/latest`) } catch (e) { s.latest = null }
    }
  } catch (e) { error.value = e.message }
}
const serverLabel = (s) => s.alias || (s.name === 'tencent' ? '广州' : s.name)
const fmtB = (b) => {
  if (!b) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(b) / Math.log(1024)), units.length - 1)
  return `${(b / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}
const monthLine = (s) => {
  const tm = s.latest?.traffic_month || {}
  const used = fmtB(tm.total_bytes || 0)
  if (tm.quota_gb > 0) return `${tm.month || ''} · ${used} / ${tm.quota_gb} GB · ${tm.used_percent}% (${tm.tz === 'UTC' ? 'UTC' : '北京'})`
  return `${tm.month || ''} · ${used} (未设额度)`
}
async function loadEvents() {
  try {
    events.value = await api('/api/alerts/events?limit=20')
  } catch (e) { error.value = e.message }
}
async function loadAudits() {
  try {
    audits.value = await api('/api/alerts/audit?limit=20')
  } catch (e) { error.value = e.message }
}
async function addRule() {
  error.value = ''
  success.value = ''
  try {
    await api('/api/alerts/rules', {
      method: 'POST',
      body: JSON.stringify(ruleForm.value)
    })
    success.value = '✅ 告警规则已添加'
    await loadRules()
  } catch (e) { error.value = e.message }
}
async function toggleRule(r) {
  try {
    await api(`/api/alerts/rules/${r.id}`, {
      method: 'PUT',
      body: JSON.stringify({ enabled: !r.enabled })
    })
    await loadRules()
  } catch (e) { error.value = e.message }
}
async function deleteRule(r) {
  error.value = ''
  success.value = ''
  try {
    await api(`/api/alerts/rules/${r.id}`, { method: 'DELETE' })
    success.value = `❌ 已删除规则 ${r.metric} ${r.operator} ${r.threshold}`
    await loadRules()
  } catch (e) { error.value = e.message }
}
const formatTs = (ts) => {
  if (!ts) return '-'
  // Force Beijing time (UTC+8)
  const ms = (ts > 1e12 ? ts : ts * 1000) + 8 * 3600 * 1000
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}/${p(d.getUTCMonth() + 1)}/${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`
}
const ruleServerLabel = (sn) => sn === '*' ? '全部服务器' : sn

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: auth.authHeaders()
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || '请求失败')
  return data
}

async function loadUsers() {
  users.value = await api('/api/auth/users')
}

async function loadInvites() {
  invites.value = await api('/api/auth/invites')
}

async function generateInvites() {
  error.value = ''
  success.value = ''
  const count = Math.min(Math.max(parseInt(inviteCount.value) || 1, 1), 100)
  const days = Math.min(Math.max(parseInt(inviteDays.value) || 7, 1), 365)
  try {
    const res = await api('/api/auth/invites', {
      method: 'POST',
      body: JSON.stringify({ count, days })
    })
    newCodes.value = res.codes
    success.value = `✅ 本次生成 ${res.codes.length} 个邀请码（${res.expires_in_days} 天内有效），已复制到剪贴板`
    // 自动复制到剪贴板
    try {
      await navigator.clipboard.writeText(res.codes.join('\n'))
    } catch (e) {
      // 剪贴板不可用时忽略
    }
    await loadInvites()
    showInvites.value = true
  } catch (e) {
    error.value = e.message
  }
}

async function addManualInvite() {
  error.value = ''
  success.value = ''
  if (!manualCode.value.trim()) {
    error.value = '请输入邀请码'
    return
  }
  try {
    const res = await api('/api/auth/invites/manual', {
      method: 'POST',
      body: JSON.stringify({
        code: manualCode.value.trim(),
        days: Math.min(Math.max(parseInt(manualDays.value) || 7, 1), 365)
      })
    })
    newCodes.value = [res.code]
    success.value = `✅ 已添加邀请码 ${res.code}（${res.expires_in_days} 天内有效）`
    manualCode.value = ''
    await loadInvites()
    showInvites.value = true
  } catch (e) {
    error.value = e.message
  }
}

function askDeleteInvite(code) {
  // 弹出自定义确认框
  confirmTarget.value = code
}

async function confirmDeleteInvite() {
  const code = confirmTarget.value
  confirmTarget.value = null
  if (!code) return
  error.value = ''
  success.value = ''
  try {
    await api('/api/auth/invites/delete', {
      method: 'POST',
      body: JSON.stringify({ code })
    })
    success.value = `❌ 已取消邀请码 ${code}`
    await loadInvites()
  } catch (e) {
    error.value = e.message
  }
}

async function toggleRole(u) {
  try {
    const newRole = u.role === 'admin' ? 'user' : 'admin'
    await api('/api/auth/users/role', {
      method: 'POST',
      body: JSON.stringify({ email: u.email, role: newRole })
    })
    await loadUsers()
  } catch (e) {
    error.value = e.message
  }
}

async function toggleDisabled(u) {
  try {
    await api('/api/auth/users/disable', {
      method: 'POST',
      body: JSON.stringify({ email: u.email, disabled: !u.disabled })
    })
    await loadUsers()
  } catch (e) {
    error.value = e.message
  }
}

async function changePassword() {
  error.value = ''
  success.value = ''
  if (newPass.value.length < 8) {
    error.value = '新密码至少 8 位'
    return
  }
  if (newPass.value !== confirmPass.value) {
    error.value = '两次密码不一致'
    return
  }
  try {
    await api('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ old_password: '', new_password: newPass.value })
    })
    success.value = '密码已修改'
    newPass.value = ''
    confirmPass.value = ''
    showChangePass.value = false
  } catch (e) {
    error.value = e.message
  }
}

function formatTime(ts) {
  if (!ts) return '-'
  // Force Beijing time (UTC+8)
  const ms = (ts > 1e12 ? ts : ts * 1000) + 8 * 3600 * 1000
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}/${p(d.getUTCMonth() + 1)}/${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`
}

// ── 登录日志 ──
const loginLogs = ref([])
const logTotal = ref(0)
const logPage = ref(1)
const LOG_PAGE_SIZE = 20
const logFilter = ref('all')     // all | success | fail
const logEmail = ref('')
const logTotalPages = computed(() => Math.max(1, Math.ceil(logTotal.value / LOG_PAGE_SIZE)))

async function loadLoginLogs() {
  const params = new URLSearchParams({ limit: LOG_PAGE_SIZE, offset: (logPage.value - 1) * LOG_PAGE_SIZE })
  if (logFilter.value === 'success') params.set('success', 1)
  if (logFilter.value === 'fail') params.set('success', 0)
  if (logEmail.value.trim()) params.set('email', logEmail.value.trim())
  try {
    const res = await api(`/api/auth/login-logs?${params}`)
    loginLogs.value = res.items
    logTotal.value = res.total
  } catch (e) { error.value = e.message }
}
function filterLogs() {
  logPage.value = 1
  loadLoginLogs()
}
function prevLogPage() {
  if (logPage.value > 1) { logPage.value--; loadLoginLogs() }
}
function nextLogPage() {
  if (logPage.value < logTotalPages.value) { logPage.value++; loadLoginLogs() }
}
function fmtUA(ua) {
  if (!ua) return '-'
  const icon = /mobile|iphone|android|ipad/i.test(ua) ? '📱' : '💻'
  // 不在此截断：桌面端由 CSS text-overflow 省略，手机端由 CSS 换行完整显示
  return `${icon} ${ua}`
}

// ── 服务探活 ──
const probes = ref([])
const showProbeForm = ref(false)
const testingId = ref(null)
const testMsg = ref('')
const PROBE_TYPES = [
  { value: 'http', label: 'HTTP(S)' },
  { value: 'tcp', label: 'TCP 端口' },
  { value: 'ping', label: 'Ping' },
  { value: 'dns', label: 'DNS 解析' }
]
const probeIcon = (t) => t === 'http' ? '🌐' : t === 'tcp' ? '🔌' : t === 'ping' ? '📡' : '🧭'
const probeLatency = (p) => p.current?.latency_ms != null ? `${p.current.latency_ms} ms` : '-'
const probeLast = (p) => p.current?.ts ? formatTs(p.current.ts) : '-'
const fmtUptime = (p) => p.uptime_24h == null ? '暂无数据' : `${p.uptime_24h}% · ${p.checks_24h} 次`

async function loadProbes() {
  try { probes.value = await api('/api/probes/rules') } catch (e) { error.value = e.message }
}

// ── 新增 / 编辑共用表单 ──
const UNIT_MULT = { s: 1, m: 60, h: 3600 }
const emptyProbeForm = () => ({ name: '', type: 'http', target: '', expected: '', interval: 60, intervalUnit: 's', timeout: 10 })
const probeForm = ref(emptyProbeForm())
const editingId = ref(null)
// 秒 → 友好单位回填：能被整除就升级单位
function pickUnit(secs) {
  if (secs >= 3600 && secs % 3600 === 0) return { v: secs / 3600, u: 'h' }
  if (secs >= 60 && secs % 60 === 0) return { v: secs / 60, u: 'm' }
  return { v: secs, u: 's' }
}
function startEdit(p) {
  const iv = pickUnit(p.interval)
  probeForm.value = { name: p.name, type: p.type, target: p.target, expected: p.expected || '', interval: iv.v, intervalUnit: iv.u, timeout: p.timeout }
  editingId.value = p.id
  showProbeForm.value = true
}
function cancelEdit() {
  editingId.value = null
  probeForm.value = emptyProbeForm()
  showProbeForm.value = false
}
async function saveProbe() {
  error.value = ''; success.value = ''
  if (!probeForm.value.name.trim() || !probeForm.value.target.trim()) {
    error.value = '请填写名称和目标'
    return
  }
  const intervalSec = Math.round(probeForm.value.interval * UNIT_MULT[probeForm.value.intervalUnit])
  if (intervalSec < 10 || intervalSec > 86400) {
    error.value = '探测间隔需在 10 秒 ~ 24 小时之间'
    return
  }
  const body = { ...probeForm.value, interval: intervalSec }
  delete body.intervalUnit
  try {
    if (editingId.value) {
      await api(`/api/probes/rules/${editingId.value}`, { method: 'PUT', body: JSON.stringify(body) })
      success.value = '✅ 探活规则已更新'
    } else {
      await api('/api/probes/rules', { method: 'POST', body: JSON.stringify(body) })
      success.value = '✅ 探活规则已添加'
    }
    cancelEdit()
    await loadProbes()
  } catch (e) { error.value = e.message }
}
async function toggleProbe(p) {
  try {
    await api(`/api/probes/rules/${p.id}`, { method: 'PUT', body: JSON.stringify({ enabled: !p.enabled }) })
    await loadProbes()
  } catch (e) { error.value = e.message }
}
async function deleteProbe(p) {
  error.value = ''; success.value = ''
  try {
    await api(`/api/probes/rules/${p.id}`, { method: 'DELETE' })
    success.value = `❌ 已删除探活规则 ${p.name}`
    await loadProbes()
  } catch (e) { error.value = e.message }
}
async function testProbe(p) {
  testingId.value = p.id
  testMsg.value = ''
  try {
    const res = await api(`/api/probes/rules/${p.id}/test`, { method: 'POST' })
    testMsg.value = `🧪 ${p.name}：${res.ok ? '✅ 可达' : '❌ 不可达'} · ${res.message || ''}`
    await loadProbes()
  } catch (e) { testMsg.value = e.message }
  finally { testingId.value = null }
}

// ── 维护模式 ──
const maintenance = ref([])
const maintForm = ref({ server_name: '*', start_at: '', end_at: '', note: '' })
const showMaintForm = ref(false)
const toLocalInput = (ts) => {
  const ms = (ts > 1e12 ? ts : ts * 1000) + 8 * 3600 * 1000
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`
}
const fromLocalInput = (v) => {
  if (!v) return 0
  return Math.floor(new Date(v + ':00').getTime() / 1000) - 8 * 3600
}
async function loadMaintenance() {
  try { maintenance.value = await api('/api/alerts/maintenance') } catch (e) { error.value = e.message }
}
async function addMaintenance() {
  error.value = ''; success.value = ''
  const start = fromLocalInput(maintForm.value.start_at)
  const end = fromLocalInput(maintForm.value.end_at)
  if (!start || !end) { error.value = '请选择开始和结束时间'; return }
  try {
    await api('/api/alerts/maintenance', { method: 'POST', body: JSON.stringify({
      server_name: maintForm.value.server_name, start_at: start, end_at: end, note: maintForm.value.note
    }) })
    maintForm.value = { server_name: '*', start_at: '', end_at: '', note: '' }
    showMaintForm.value = false
    success.value = '✅ 维护窗口已创建'
    await loadMaintenance()
  } catch (e) { error.value = e.message }
}
async function deleteMaintenance(w) {
  try {
    await api(`/api/alerts/maintenance/${w.id}`, { method: 'DELETE' })
    await loadMaintenance()
  } catch (e) { error.value = e.message }
}
const maintStatus = (w) => w.active ? '🔴 生效中' : w.expired ? '已结束' : '待生效'
const fmtRange = (w) => `${formatTs(w.start_at)} ~ ${formatTs(w.end_at)}`

// ── Agent 健康 ──
const agentHealth = ref([])
async function loadAgentHealth() {
  try { agentHealth.value = await api('/api/agents-health') } catch (e) { error.value = e.message }
}
const fmtAge = (a) => {
  // 相对时间 + 绝对时间（北京时间），一眼看清上次上报时刻
  const rel = a.online ? `${a.last_age} 秒前` : `${a.last_age} 秒前（离线）`
  return `${rel} · ${formatTs(a.last_ts)}`
}

// ── 自定义监控项（管理页配置 → 数据库 → agent 拉取执行）──
const customCmds = ref([])
const customForm = ref({ server_name: 'oracle', name: '', cmd: '', interval: 60, intervalUnit: 's', unit: '', timeout: 5 })
const showCustomForm = ref(false)
const editingCustomId = ref(null)
const emptyCustomForm = () => ({ server_name: 'oracle', name: '', cmd: '', interval: 60, intervalUnit: 's', unit: '', timeout: 5 })

async function loadCustomCmds() {
  try { customCmds.value = await api('/api/custom-commands') } catch (e) { error.value = e.message }
}
function startEditCustom(c) {
  const iv = pickUnit(c.interval)
  customForm.value = { server_name: c.server_name, name: c.name, cmd: c.cmd, interval: iv.v, intervalUnit: iv.u, unit: c.unit || '', timeout: c.timeout }
  editingCustomId.value = c.id
  showCustomForm.value = true
}
function cancelEditCustom() {
  editingCustomId.value = null
  customForm.value = emptyCustomForm()
  showCustomForm.value = false
}
async function saveCustom() {
  error.value = ''; success.value = ''
  if (!customForm.value.name.trim() || !customForm.value.cmd.trim()) {
    error.value = '请填写名称和命令'
    return
  }
  const intervalSec = Math.round(customForm.value.interval * UNIT_MULT[customForm.value.intervalUnit])
  if (intervalSec < 10 || intervalSec > 86400) {
    error.value = '执行间隔需在 10 秒 ~ 24 小时之间'
    return
  }
  const body = { server_name: customForm.value.server_name, name: customForm.value.name, cmd: customForm.value.cmd, interval: intervalSec, unit: customForm.value.unit, timeout: customForm.value.timeout }
  try {
    if (editingCustomId.value) {
      await api(`/api/custom-commands/${editingCustomId.value}`, { method: 'PUT', body: JSON.stringify(body) })
      success.value = '✅ 自定义监控项已更新'
    } else {
      await api('/api/custom-commands', { method: 'POST', body: JSON.stringify(body) })
      success.value = '✅ 自定义监控项已添加（agent 1 分钟内生效）'
    }
    cancelEditCustom()
    await loadCustomCmds()
  } catch (e) { error.value = e.message }
}
async function toggleCustom(c) {
  try {
    await api(`/api/custom-commands/${c.id}`, { method: 'PUT', body: JSON.stringify({ enabled: !c.enabled }) })
    await loadCustomCmds()
  } catch (e) { error.value = e.message }
}
async function deleteCustom(c) {
  error.value = ''; success.value = ''
  try {
    await api(`/api/custom-commands/${c.id}`, { method: 'DELETE' })
    success.value = `❌ 已删除自定义监控项 ${c.name}`
    await loadCustomCmds()
  } catch (e) { error.value = e.message }
}

const CHANNEL_NAMES = { telegram: 'Telegram', bark: 'Bark' }

onMounted(async () => {
  if (!auth.isAdmin()) {
    router.push('/')
    return
  }
  try {
    await loadUsers()
    await loadInvites()
    await loadServers()
    await loadRules()
    await loadEvents()
    await loadAudits()
    await loadLoginLogs()
    await loadProbes()
    await loadMaintenance()
    await loadAgentHealth()
    await loadCustomCmds()
  } catch (e) {
    error.value = e.message
  }
})
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div>
        <h1 class="section-title">管理后台</h1>
        <p class="subtitle">邀请码 · 用户管理 · 账号设置</p>
      </div>
      <div class="header-right">
        <button class="btn-secondary" @click="showInvites = !showInvites">
          {{ showInvites ? '收起邀请码' : '查看邀请码' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="alert error">{{ error }}</div>
    <div v-if="success" class="alert success">{{ success }}</div>

    <!-- 邀请码区 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>🎟️ 邀请码管理</h3>
        <div class="btn-group">
          <input
            v-model.number="inviteCount"
            type="number"
            min="1"
            max="100"
            class="count-input"
            placeholder="数量"
            title="生成数量(1-100)"
          />
          <input
            v-model.number="inviteDays"
            type="number"
            min="1"
            max="365"
            class="count-input"
            placeholder="天数"
            title="有效期天数(1-365)"
          />
          <button class="btn-primary" :disabled="loading" @click="generateInvites">
            {{ loading ? '生成中...' : '生成邀请码' }}
          </button>
        </div>
      </div>
      <div class="section-hint">数量(1-100) + 有效期天数(1-365)，新邀请码自动复制到剪贴板</div>

      <!-- 自定义邀请码(按钮触发展开) -->
      <button class="btn-secondary manual-toggle" @click="showManual = !showManual">
        {{ showManual ? '收起自定义邀请码 ▲' : '自定义邀请码 ▼' }}
      </button>
      <div v-if="showManual" class="manual-row">
        <input
          v-model="manualCode"
          type="text"
          class="manual-input"
          placeholder="自定义邀请码,如 DFSHMILY2026"
          maxlength="32"
        />
        <input
          v-model.number="manualDays"
          type="number"
          min="1"
          max="365"
          class="count-input"
          placeholder="天数"
          title="有效期(天)"
        />
        <button class="btn-secondary" :disabled="loading" @click="addManualInvite">添加</button>
      </div>
      <div v-if="showManual" class="section-hint">自己指定邀请码文字和有效期(1-365 天)</div>

      <div v-if="showInvites" class="invite-list">
        <div v-if="invites.length === 0" class="empty">暂无邀请码</div>
        <template v-for="inv in invites" :key="inv.code">
          <div
            v-if="newCodes.includes(inv.code)"
            class="invite-item new"
          >
            <code class="invite-code">{{ inv.code }}</code>
            <span class="unused-tag">🆕 新生成 · {{ formatTime(inv.expires_at) }} 过期</span>
          </div>
        </template>
        <div
          v-for="inv in invites.filter(i => !newCodes.includes(i.code))"
          :key="inv.code"
          class="invite-item"
          :class="{ used: inv.used_by }"
        >
          <code class="invite-code">{{ inv.code }}</code>
          <div class="invite-right">
            <span v-if="inv.used_by" class="used-tag">已被 {{ inv.used_by }} 使用</span>
            <span v-else class="unused-tag">未使用 · {{ formatTime(inv.expires_at) }} 过期</span>
            <button
              v-if="!inv.used_by"
              class="delete-btn"
              title="取消此邀请码"
              @click="askDeleteInvite(inv.code)"
            >取消</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 取消邀请码确认弹窗 -->
    <div v-if="confirmTarget" class="modal-mask" @click.self="confirmTarget = null">
      <div class="modal-box">
        <h3>取消邀请码</h3>
        <p>确定要取消 <code class="modal-code">{{ confirmTarget }}</code> 吗？</p>
        <p class="modal-warn">取消后该邀请码立即失效，对方将无法用它注册。</p>
        <div class="modal-actions">
          <button class="btn-secondary" @click="confirmTarget = null">再想想</button>
          <button class="btn-danger" @click="confirmDeleteInvite">确认取消</button>
        </div>
      </div>
    </div>

    <!-- 用户列表 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>👥 用户管理</h3>
      </div>
      <div class="user-table">
        <div class="user-row header">
          <span>邮箱</span><span>角色</span><span>状态</span><span>注册时间</span><span>操作</span>
        </div>
        <div v-for="u in users" :key="u.id" class="user-row">
          <span class="user-email">{{ u.email }}</span>
          <span><span class="role-badge" :class="u.role">{{ u.email === ROOT_EMAIL ? '超级管理员' : (u.role === 'admin' ? '管理员' : '用户') }}</span></span>
          <span>
            <span class="status-dot-mini" :class="{ on: !u.disabled }"></span>
            {{ u.disabled ? '已禁用' : '正常' }}
          </span>
          <span class="user-time">{{ formatTime(u.created_at) }}</span>
          <span class="user-actions">
            <template v-if="u.email !== auth.user?.email">
              <button v-if="isRoot" class="link-btn" @click="toggleRole(u)">
                {{ u.role === 'admin' ? '取消管理' : '设为管理' }}
              </button>
              <button v-if="isRoot || u.role !== 'admin'" class="link-btn danger" @click="toggleDisabled(u)">
                {{ u.disabled ? '启用' : '禁用' }}
              </button>
              <span v-if="!isRoot && u.role === 'admin'" class="muted-tag">仅超管可操作</span>
            </template>
            <span v-else class="self-tag">自己</span>
          </span>
        </div>
      </div>
    </div>

    <!-- 告警规则 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>🚨 告警规则</h3>
        <div class="btn-group">
          <span v-if="testResult" class="test-result">{{ testResult }}</span>
          <button class="btn-secondary" :disabled="testNotifying" @click="testNotify">
            {{ testNotifying ? '发送中...' : '📨 通知测试' }}
          </button>
        </div>
      </div>
      <div class="section-hint">触发后推送到 Telegram / Bark，恢复后自动推送「已恢复」（每规则 30 分钟冷却）</div>
      <div class="rule-form">
        <select v-model="ruleForm.server_name" class="count-input">
          <option value="*">全部服务器</option>
          <option value="oracle">oracle</option>
          <option value="tencent">tencent</option>
        </select>
        <select v-model="ruleForm.metric" class="count-input">
          <option v-for="m in METRIC_OPTIONS" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
        <select v-model="ruleForm.operator" class="count-input" style="width:70px">
          <option v-for="op in OP_OPTIONS" :key="op" :value="op">{{ op }}</option>
        </select>
        <input v-model.number="ruleForm.threshold" type="number" class="count-input" placeholder="阈值" style="width:90px" />
        <button class="btn-primary" @click="addRule">添加规则</button>
      </div>
      <div class="user-table">
        <div class="user-row header">
          <span>服务器</span><span>指标</span><span>条件</span><span>状态</span><span>操作</span>
        </div>
        <div v-for="r in rules" :key="r.id" class="user-row">
          <span>{{ ruleServerLabel(r.server_name) }}</span>
          <span>{{ r.metric }}</span>
          <span>{{ r.operator }} {{ r.threshold }}</span>
          <span>
            <span class="status-dot-mini" :class="{ on: r.enabled }"></span>
            {{ r.enabled ? '启用' : '停用' }}
          </span>
          <span class="user-actions">
            <button class="link-btn" @click="toggleRule(r)">{{ r.enabled ? '停用' : '启用' }}</button>
            <button class="link-btn danger" @click="deleteRule(r)">删除</button>
          </span>
        </div>
        <div v-if="rules.length === 0" class="user-row"><span class="muted-tag">还没有告警规则</span></div>
      </div>
    </div>

    <!-- 告警统计 + 事件/审计 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>📊 告警统计</h3>
      </div>
      <AlertStatsChart :days="14" />
    </div>

    <!-- 本月流量 · 近30天 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>📅 本月流量 · 近 30 天</h3>
      </div>
      <div v-if="servers.length === 0" class="muted-tag">暂无服务器数据</div>
      <div v-else class="traffic-grid">
        <div v-for="s in servers" :key="s.name" class="traffic-server">
          <div class="traffic-server-head">
            <span class="traffic-server-name">{{ serverLabel(s) }}</span>
            <span class="traffic-server-line">{{ monthLine(s) }}</span>
          </div>
          <TrafficDailyChart :server-name="s.name" :days="30" />
        </div>
      </div>
    </div>

    <!-- 告警事件 + 审计日志 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>📜 告警记录与审计日志</h3>
      </div>
      <div class="logs-grid">
        <div>
          <h4 style="margin:8px 0 8px;font-size:13px;color:var(--text-secondary)">告警事件</h4>
          <div v-for="e in events" :key="e.id" class="log-item" :class="{ offline: e.kind === 'offline' }">
            <span class="log-time">{{ formatTs(e.created_at) }}</span>
            <span class="log-msg">{{ e.message }}</span>
          </div>
          <div v-if="events.length === 0" class="muted-tag">暂无告警记录</div>
        </div>
        <div>
          <h4 style="margin:8px 0 8px;font-size:13px;color:var(--text-secondary)">管理操作</h4>
          <div v-for="a in audits" :key="a.id" class="log-item">
            <span class="log-time">{{ formatTs(a.created_at) }}</span>
            <span class="log-msg">{{ a.email }} · {{ a.action }} {{ a.detail || '' }}</span>
          </div>
          <div v-if="audits.length === 0" class="muted-tag">暂无操作记录</div>
        </div>
      </div>
    </div>

    <!-- 服务探活 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>🔍 服务探活</h3>
        <button class="btn-secondary" @click="showProbeForm ? cancelEdit() : (showProbeForm = true)">
          {{ showProbeForm ? '收起' : '＋ 添加规则' }}
        </button>
      </div>
      <div class="section-hint">从本机探测 HTTP / TCP 端口 / Ping / DNS，判断服务是否"用户可达"· 失败推送通知，恢复自动提醒（30 分钟冷却）</div>
      <div v-if="showProbeForm" class="probe-form">
        <input v-model="probeForm.name" class="probe-input" placeholder="名称，如：面板网站" maxlength="64" />
        <select v-model="probeForm.type" class="count-input" style="width:110px">
          <option v-for="t in PROBE_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
        <input v-model="probeForm.target" class="probe-input" placeholder="目标：https://… / host:port / IP / 域名" maxlength="512" />
        <input v-model="probeForm.expected" class="probe-input" style="max-width:150px" placeholder="关键词(可选)" maxlength="256" />
        <span class="interval-unit">
          <input v-model.number="probeForm.interval" type="number" class="count-input" min="1" max="86400" title="探测间隔" placeholder="60" />
          <select v-model="probeForm.intervalUnit" class="count-input" style="width:74px" title="间隔单位">
            <option value="s">秒</option>
            <option value="m">分钟</option>
            <option value="h">小时</option>
          </select>
        </span>
        <button class="btn-primary" @click="saveProbe">{{ editingId ? '保存修改' : '添加' }}</button>
        <button v-if="editingId" class="btn-secondary" @click="cancelEdit">取消</button>
      </div>
      <div v-if="testMsg" class="test-result" style="display:block;margin-bottom:8px">{{ testMsg }}</div>
      <div class="probe-table">
        <div class="probe-row header">
          <span>名称</span><span>类型</span><span>目标</span><span>状态</span><span>延迟</span><span>24h 可用率</span><span>操作</span>
        </div>
        <div v-for="p in probes" :key="p.id" class="probe-row">
          <span class="probe-name">{{ p.name }}</span>
          <span class="probe-type">{{ probeIcon(p.type) }} {{ p.type.toUpperCase() }}</span>
          <span class="probe-target" :title="p.target">{{ p.target }}</span>
          <span>
            <span class="status-dot-mini" :class="{ on: p.current?.ok }"></span>
            <span v-if="!p.current">待测</span>
            <span v-else>{{ p.current.ok ? '正常' : '异常' }}</span>
            <span v-if="p.current" class="muted-tag"> · {{ probeLast(p) }}</span>
          </span>
          <span class="probe-latency">{{ probeLatency(p) }}</span>
          <span class="probe-uptime">{{ fmtUptime(p) }}</span>
          <span class="probe-actions">
            <button class="link-btn" :disabled="testingId === p.id" @click="testProbe(p)">
              {{ testingId === p.id ? '测试中…' : '测试' }}
            </button>
            <button class="link-btn" @click="startEdit(p)">编辑</button>
            <button class="link-btn" @click="toggleProbe(p)">{{ p.enabled ? '停用' : '启用' }}</button>
            <button class="link-btn danger" @click="deleteProbe(p)">删除</button>
          </span>
        </div>
        <div v-if="probes.length === 0" class="probe-row"><span class="muted-tag">还没有探活规则 · 点击右上角"添加规则"创建第一个</span></div>
      </div>
    </div>

    <!-- Agent 健康 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>🤖 Agent 健康</h3>
        <button class="btn-secondary" @click="loadAgentHealth">🔄 刷新</button>
      </div>
      <div class="section-hint">每台服务器的数据上报健康度：版本 / 最后上报时间 / 推送频率</div>
      <div class="agent-table">
        <div class="agent-row header">
          <span>服务器</span><span>版本</span><span>最后上报</span><span>10分钟推送</span><span>状态</span>
        </div>
        <div v-for="a in agentHealth" :key="a.server_name" class="agent-row">
          <span class="user-email">{{ a.server_name }}</span>
          <span>{{ a.version || '-' }}</span>
          <span class="user-time">{{ fmtAge(a) }}</span>
          <span>{{ a.pushes_10min }} 次</span>
          <span>
            <span class="status-dot-mini" :class="{ on: a.online }"></span>
            {{ a.online ? '在线' : '离线' }}
          </span>
        </div>
        <div v-if="agentHealth.length === 0" class="agent-row"><span class="muted-tag">暂无数据</span></div>
      </div>
    </div>

    <!-- 自定义监控项 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>📈 自定义监控项</h3>
        <button class="btn-secondary" @click="showCustomForm ? cancelEditCustom() : (showCustomForm = true)">
          {{ showCustomForm ? '收起' : '＋ 添加命令' }}
        </button>
      </div>
      <div class="section-hint">配置任意命令，由对应服务器 agent 定期执行并上报到详情页概览（agent 约 1 分钟内生效）· ⚠️ 不要放会泄露敏感信息的命令</div>
      <div v-if="showCustomForm" class="probe-form">
        <select v-model="customForm.server_name" class="count-input" style="width:100px">
          <option value="oracle">oracle</option>
          <option value="tencent">tencent</option>
        </select>
        <input v-model="customForm.name" class="probe-input" style="max-width:140px" placeholder="名称，如：CPU温度" maxlength="32" />
        <input v-model="customForm.cmd" class="probe-input" placeholder="命令，如：df -BG / | awk 'NR==2{print $4}'" maxlength="512" />
        <input v-model="customForm.unit" class="probe-input" style="max-width:90px" placeholder="单位(可选)" maxlength="16" />
        <span class="interval-unit">
          <input v-model.number="customForm.interval" type="number" class="count-input" min="1" max="86400" title="执行间隔" placeholder="60" />
          <select v-model="customForm.intervalUnit" class="count-input" style="width:74px" title="间隔单位">
            <option value="s">秒</option>
            <option value="m">分钟</option>
            <option value="h">小时</option>
          </select>
        </span>
        <button class="btn-primary" @click="saveCustom">{{ editingCustomId ? '保存修改' : '添加' }}</button>
        <button v-if="editingCustomId" class="btn-secondary" @click="cancelEditCustom">取消</button>
      </div>
      <div class="probe-table">
        <div class="probe-row header custom-row">
          <span>服务器</span><span>名称</span><span>命令</span><span>间隔</span><span>状态</span><span>操作</span>
        </div>
        <div v-for="c in customCmds" :key="c.id" class="probe-row custom-row">
          <span>{{ c.server_name }}</span>
          <span class="probe-name">{{ c.name }}</span>
          <span class="probe-target" :title="c.cmd">{{ c.cmd }}</span>
          <span class="probe-latency">{{ pickUnit(c.interval).v }}{{ pickUnit(c.interval).u === 's' ? '秒' : pickUnit(c.interval).u === 'm' ? '分钟' : '小时' }}</span>
          <span>
            <span class="status-dot-mini" :class="{ on: c.enabled }"></span>
            {{ c.enabled ? '启用' : '停用' }}
          </span>
          <span class="probe-actions">
            <button class="link-btn" @click="startEditCustom(c)">编辑</button>
            <button class="link-btn" @click="toggleCustom(c)">{{ c.enabled ? '停用' : '启用' }}</button>
            <button class="link-btn danger" @click="deleteCustom(c)">删除</button>
          </span>
        </div>
        <div v-if="customCmds.length === 0" class="probe-row"><span class="muted-tag">还没有自定义监控项 · 点击右上角"添加命令"创建</span></div>
      </div>
    </div>

    <!-- 维护模式 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>🛠 维护模式</h3>
        <button class="btn-secondary" @click="showMaintForm = !showMaintForm">
          {{ showMaintForm ? '收起' : '＋ 新建窗口' }}
        </button>
      </div>
      <div class="section-hint">维护窗口内对应服务器的告警 / 离线通知静默（事件仍会记录）</div>
      <div v-if="showMaintForm" class="maint-form">
        <select v-model="maintForm.server_name" class="count-input" style="width:110px">
          <option value="*">全部服务器</option>
          <option value="oracle">oracle</option>
          <option value="tencent">tencent</option>
        </select>
        <input v-model="maintForm.start_at" type="datetime-local" class="probe-input" />
        <input v-model="maintForm.end_at" type="datetime-local" class="probe-input" />
        <input v-model="maintForm.note" class="probe-input" placeholder="备注，如：重装系统" maxlength="256" />
        <button class="btn-primary" @click="addMaintenance">创建</button>
      </div>
      <div v-if="maintenance.length === 0" class="muted-tag" style="padding:8px 0">暂无维护窗口</div>
      <div v-for="w in maintenance" :key="w.id" class="maint-item">
        <span class="maint-status" :class="{ active: w.active }">{{ maintStatus(w) }}</span>
        <span class="maint-server">{{ w.server_name === '*' ? '全部服务器' : w.server_name }}</span>
        <span class="maint-range">{{ fmtRange(w) }}</span>
        <span class="maint-note">{{ w.note || '' }}</span>
        <button class="delete-btn" @click="deleteMaintenance(w)">删除</button>
      </div>
    </div>

    <!-- 登录日志 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>🔐 登录日志</h3>
        <button class="btn-secondary" @click="loadLoginLogs">🔄 刷新</button>
      </div>
      <div class="section-hint">最近 30 天登录记录 · 同一账号连续 5 次失败锁定 15 分钟，同一 IP 累计 10 次失败锁定 15 分钟</div>
      <div class="log-filter-row">
        <select v-model="logFilter" class="count-input" style="width:110px" @change="filterLogs">
          <option value="all">全部</option>
          <option value="success">✅ 成功</option>
          <option value="fail">❌ 失败</option>
        </select>
        <input v-model="logEmail" class="log-search" placeholder="按邮箱搜索…" @keyup.enter="filterLogs" />
        <button class="btn-secondary" @click="filterLogs">搜索</button>
      </div>
      <div class="login-table">
        <div class="login-row header">
          <span style="width:120px">时间</span><span>邮箱</span><span>IP</span><span>设备</span><span style="width:56px">结果</span>
        </div>
        <div v-for="l in loginLogs" :key="l.id" class="login-row">
          <span class="user-time">{{ formatTs(l.created_at) }}</span>
          <span class="user-email">{{ l.email }}</span>
          <span class="log-ip"><i class="log-label">IP</i>{{ l.ip || '-' }}</span>
          <span class="log-ua" :title="l.user_agent || ''"><i class="log-label">设备</i>{{ fmtUA(l.user_agent) }}</span>
          <span class="log-result">
            <span class="login-dot" :class="{ ok: l.success }"></span>
            {{ l.success ? '成功' : '失败' }}
          </span>
        </div>
        <div v-if="loginLogs.length === 0" class="login-row"><span class="muted-tag">暂无登录记录</span></div>
      </div>
      <div class="log-pager">
        <button class="btn-secondary" :disabled="logPage <= 1" @click="prevLogPage">← 上一页</button>
        <span class="muted-tag">{{ logTotal === 0 ? '0 条记录' : `第 ${logPage} / ${logTotalPages} 页 · 共 ${logTotal} 条` }}</span>
        <button class="btn-secondary" :disabled="logPage >= logTotalPages" @click="nextLogPage">下一页 →</button>
      </div>
    </div>

    <!-- 改密码 -->
    <div class="glass-card section">
      <div class="section-head">
        <h3>🔑 修改密码</h3>
        <button class="btn-secondary" @click="showChangePass = !showChangePass">
          {{ showChangePass ? '收起' : '修改' }}
        </button>
      </div>
      <div v-if="showChangePass" class="pass-form">
        <input v-model="newPass" type="password" placeholder="新密码（至少 8 位）" />
        <input v-model="confirmPass" type="password" placeholder="确认新密码" />
        <button class="btn-primary" @click="changePassword">确认修改</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  max-width: 900px;
  margin: 0 auto;
  padding: 32px 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.subtitle {
  color: var(--text-tertiary);
  font-size: 14px;
  margin-top: 4px;
}

.alert {
  padding: 12px 16px;
  border-radius: 10px;
  margin-bottom: 16px;
  font-size: 14px;
}
.alert.error { background: rgba(255, 59, 48, 0.1); color: var(--status-red); }
.alert.success { background: rgba(52, 199, 89, 0.12); color: var(--status-green); }

.section {
  padding: 20px;
  margin-bottom: 20px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.section-head h3 {
  font-size: 16px;
  font-weight: 600;
}

.btn-group { display: flex; gap: 8px; align-items: center; }

.count-input {
  width: 70px;
  padding: 8px 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 10px;
  font-size: 14px;
  text-align: center;
  outline: none;
  transition: border-color 0.2s;
}

.count-input:focus {
  border-color: var(--purple-500, #8b5cf6);
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.12);
}

.section-hint {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: -4px 0 12px;
}

.test-result {
  font-size: 13px;
  font-weight: 600;
  color: var(--status-green, #34c759);
  margin-right: 4px;
}

/* 本月流量 · 近30天 */
.traffic-grid {
  display: grid;
  /* min(100%, 420px)：窄屏时收缩到容器宽，避免卡片溢出屏幕 */
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr));
  gap: 20px;
}

.traffic-server {
  padding: 14px;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 12px;
}

.traffic-server-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.traffic-server-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.traffic-server-line {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  min-width: 0;
  overflow-wrap: anywhere;
}

.manual-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 8px 0;
  flex-wrap: wrap;
}

.manual-toggle {
  margin: 4px 0 8px;
}

.manual-input {
  flex: 1;
  min-width: 180px;
  padding: 8px 12px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 10px;
  font-size: 14px;
  font-family: 'SF Mono', monospace;
  letter-spacing: 1px;
  text-transform: uppercase;
  outline: none;
  transition: border-color 0.2s;
}

.manual-input:focus {
  border-color: var(--purple-500, #8b5cf6);
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.12);
}
.btn-primary {
  padding: 8px 16px;
  border: none;
  border-radius: 10px;
  background: var(--purple-600, #7c3aed);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-secondary {
  padding: 8px 16px;
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 10px;
  background: #fff;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.invite-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 300px;
  overflow-y: auto;
}
.invite-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.03);
}

.invite-item.new {
  background: rgba(124, 58, 237, 0.08);
  border: 1px solid rgba(124, 58, 237, 0.25);
}
.invite-code {
  font-family: 'SF Mono', monospace;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 2px;
}
.invite-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.delete-btn {
  padding: 3px 10px;
  border: 1px solid rgba(255, 59, 48, 0.3);
  border-radius: 8px;
  background: rgba(255, 59, 48, 0.06);
  color: var(--status-red);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.delete-btn:hover {
  background: rgba(255, 59, 48, 0.12);
}

.used-tag { font-size: 12px; color: var(--text-tertiary); }
.unused-tag { font-size: 12px; color: var(--status-green); }
.empty { color: var(--text-tertiary); padding: 16px; text-align: center; }

.user-table {
  display: flex;
  flex-direction: column;
}
.user-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1.4fr 1.6fr;
  gap: 10px;
  align-items: center;
  padding: 10px 8px;
  border-bottom: 1px solid rgba(0,0,0,0.05);
  font-size: 13px;
}
.user-row.header {
  color: var(--text-tertiary);
  font-weight: 600;
  font-size: 12px;
}
.user-email { font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
.role-badge {
  padding: 2px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
}
.role-badge.admin { background: rgba(124, 58, 237, 0.12); color: var(--purple-600, #7c3aed); }
.role-badge.user { background: rgba(0,0,0,0.06); color: var(--text-secondary); }
.status-dot-mini {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #c7c7cc;
  margin-right: 4px;
}
.status-dot-mini.on { background: var(--status-green); }
.user-time { color: var(--text-tertiary); font-size: 12px; }
.user-actions { display: flex; gap: 10px; }
.link-btn {
  border: none;
  background: none;
  color: var(--purple-500, #8b5cf6);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  padding: 0;
}
.link-btn.danger { color: var(--status-red); }
.self-tag { color: var(--text-tertiary); font-size: 12px; }
.muted-tag { color: var(--text-tertiary); font-size: 12px; }

.rule-form {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 14px;
}

.logs-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

/* ── 登录日志 ── */
.log-filter-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.log-search {
  flex: 1;
  min-width: 160px;
  padding: 8px 12px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 10px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}
.log-search:focus {
  border-color: var(--purple-500, #8b5cf6);
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.12);
}
.login-table {
  display: flex;
  flex-direction: column;
}
.login-row {
  display: grid;
  grid-template-columns: 120px 1.6fr 1fr 1.6fr 56px;
  gap: 10px;
  align-items: center;
  padding: 10px 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  font-size: 13px;
  min-width: 0;
}
.login-row.header {
  color: var(--text-tertiary);
  font-weight: 600;
  font-size: 12px;
}
.login-row.header span:last-child,
.login-row > span:last-child {
  text-align: right;
}
.log-label {
  display: none;
  font-style: normal;
  color: var(--text-tertiary);
  font-size: 11px;
  margin-right: 6px;
}
.log-ip {
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.log-ua {
  color: var(--text-tertiary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.login-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--status-red);
  margin-right: 4px;
  vertical-align: middle;
}
.login-dot.ok { background: var(--status-green); }
.log-pager {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 14px;
  gap: 8px;
}

/* ── 服务探活 ── */
.probe-form {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 14px;
}
.probe-input {
  flex: 1;
  min-width: 160px;
  padding: 8px 12px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 10px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
}
.probe-input:focus {
  border-color: var(--purple-500, #8b5cf6);
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.12);
}
.interval-unit {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.probe-table { display: flex; flex-direction: column; }
.probe-row {
  display: grid;
  grid-template-columns: 1.1fr 0.7fr 1.6fr 1.2fr 0.7fr 0.9fr 1.3fr;
  gap: 10px;
  align-items: center;
  padding: 10px 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  font-size: 13px;
  min-width: 0;
}
/* 自定义监控项：6 列布局（覆盖 probe-row 的 7 列；手机端 media query 仍生效） */
.probe-row.custom-row {
  grid-template-columns: 0.8fr 1fr 2.4fr 0.8fr 0.9fr 1.4fr;
}
.probe-row.header {
  color: var(--text-tertiary);
  font-weight: 600;
  font-size: 12px;
}
.probe-name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.probe-target {
  color: var(--text-secondary);
  font-family: 'SF Mono', monospace;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.probe-latency { font-variant-numeric: tabular-nums; color: var(--text-secondary); }
.probe-uptime { color: var(--text-secondary); font-size: 12px; }
.probe-actions { display: flex; gap: 10px; }

/* ── Agent 健康 ── */
.agent-table { display: flex; flex-direction: column; }
.agent-row {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1.4fr 1fr 1fr;
  gap: 10px;
  align-items: center;
  padding: 10px 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  font-size: 13px;
}
.agent-row.header {
  color: var(--text-tertiary);
  font-weight: 600;
  font-size: 12px;
}

/* ── 维护模式 ── */
.maint-form {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 14px;
}
.maint-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 10px 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  font-size: 13px;
  flex-wrap: wrap;
}
.maint-status {
  font-weight: 600;
  color: var(--text-tertiary);
  font-size: 12px;
}
.maint-status.active { color: var(--status-red); }
.maint-server { font-weight: 600; }
.maint-range { color: var(--text-secondary); font-variant-numeric: tabular-nums; font-size: 12px; }
.maint-note { color: var(--text-tertiary); font-size: 12px; flex: 1; min-width: 80px; }

/* 手机端：探活/维护区块纵向排列 */
@media (max-width: 720px) {
  .probe-row { grid-template-columns: 1fr 1fr; row-gap: 4px; padding: 12px 8px; }
  .probe-row.header { display: none; }
  .probe-row > span:nth-child(1) { grid-column: 1 / -1; grid-row: 1; }
  .probe-row > span:nth-child(2) { grid-column: 1; grid-row: 2; }
  .probe-row > span:nth-child(4) { grid-column: 2; grid-row: 2; justify-self: end; }
  .probe-row > span:nth-child(3) { grid-column: 1 / -1; grid-row: 3; white-space: normal; word-break: break-all; }
  .probe-row > span:nth-child(5) { grid-column: 1; grid-row: 4; }
  .probe-row > span:nth-child(6) { grid-column: 2; grid-row: 4; justify-self: end; }
  .probe-row > span:nth-child(7) { grid-column: 1 / -1; grid-row: 5; }
  .agent-row { grid-template-columns: 1fr 1fr; row-gap: 4px; padding: 12px 8px; }
  .agent-row.header { display: none; }
  .maint-item { flex-direction: column; align-items: flex-start; gap: 6px; }
}

/* 手机端：每条记录变卡片，字段逐行完整显示 */
@media (max-width: 720px) {
  .login-row {
    grid-template-columns: 1fr auto;
    row-gap: 4px;
    padding: 12px 8px;
  }
  .login-row.header { display: none; }
  .login-row > span:nth-child(1) { grid-column: 1; grid-row: 1; }
  .login-row > span:nth-child(5) { grid-column: 2; grid-row: 1; justify-self: end; }
  .login-row > span:nth-child(2) { grid-column: 1 / -1; grid-row: 2; }
  .login-row > span:nth-child(3) { grid-column: 1 / -1; grid-row: 3; }
  .login-row > span:nth-child(4) {
    grid-column: 1 / -1;
    grid-row: 4;
    white-space: normal;
    word-break: break-all;
  }
  .log-label { display: inline; }
}

@media (max-width: 720px) {
  .logs-grid { grid-template-columns: 1fr; }
  /* 手机端：服务器名与月流量汇总纵向排列，文字换行不溢出 */
  .traffic-server-head { flex-direction: column; align-items: flex-start; gap: 4px; }
}

.log-item {
  display: flex;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  font-size: 12px;
  align-items: baseline;
}

.log-item.offline .log-msg { color: var(--status-red); }

.log-time {
  flex-shrink: 0;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
  font-size: 11px;
}

.log-msg {
  color: var(--text-secondary);
  word-break: break-all;
}

.pass-form {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.pass-form input {
  flex: 1;
  min-width: 180px;
  padding: 10px 14px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 10px;
  font-size: 14px;
}

/* ── 确认弹窗 ── */
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  animation: fadeIn 0.2s ease;
}

.modal-box {
  background: #fff;
  border-radius: 20px;
  padding: 28px 24px;
  max-width: 360px;
  width: 100%;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  animation: slideUp 0.25s cubic-bezier(0.22, 1, 0.36, 1);
}

.modal-box h3 {
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 12px;
  color: var(--text-primary);
}

.modal-box p {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0 0 8px;
}

.modal-code {
  font-family: 'SF Mono', monospace;
  font-weight: 700;
  color: var(--purple-600, #7c3aed);
  background: rgba(124, 58, 237, 0.08);
  padding: 2px 8px;
  border-radius: 6px;
}

.modal-warn {
  font-size: 12px !important;
  color: var(--text-tertiary) !important;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  margin-top: 20px;
}

.btn-danger {
  padding: 10px 18px;
  border: none;
  border-radius: 10px;
  background: var(--status-red, #ff3b30);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-danger:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(255, 59, 48, 0.35);
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}
</style>
