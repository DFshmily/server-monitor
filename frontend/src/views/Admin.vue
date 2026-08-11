<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

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
  { value: 'net_out', label: '网络出速率 B/s' }
]
const OP_OPTIONS = ['>', '>=', '<', '<=']

async function loadRules() {
  try {
    rules.value = await api('/api/alerts/rules')
  } catch (e) { error.value = e.message }
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

onMounted(async () => {
  if (!auth.isAdmin()) {
    router.push('/')
    return
  }
  try {
    await loadUsers()
    await loadInvites()
    await loadRules()
    await loadEvents()
    await loadAudits()
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
        <span class="subtitle">触发后推送到 Telegram（每规则 30 分钟冷却）</span>
      </div>
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

@media (max-width: 720px) {
  .logs-grid { grid-template-columns: 1fr; }
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
