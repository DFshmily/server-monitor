import { defineStore } from 'pinia'
import { ref } from 'vue'

const TOKEN_KEY = 'monitor_token'
const USER_KEY = 'monitor_user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const user = ref(null)

  try {
    const saved = localStorage.getItem(USER_KEY)
    if (saved) user.value = JSON.parse(saved)
  } catch (e) {
    user.value = null
  }

  function authHeaders() {
    return token.value
      ? { 'Content-Type': 'application/json', Authorization: `Bearer ${token.value}` }
      : { 'Content-Type': 'application/json' }
  }

  async function login(email, password, remember) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, remember })
    })
    // Cloudflare 质询/错误页返回 HTML, res.json() 会抛
    // "The string did not match the expected pattern" —— 拦下来给友好提示
    const ct = res.headers.get('content-type') || ''
    if (!ct.includes('application/json')) {
      throw new Error('网络验证中，请稍等几秒后重试')
    }
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '登录失败')
    token.value = data.token
    user.value = { email: data.email, role: data.role }
    localStorage.setItem(TOKEN_KEY, data.token)
    localStorage.setItem(USER_KEY, JSON.stringify(user.value))
    return data
  }

  async function register(email, password, inviteCode) {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, invite_code: inviteCode })
    })
    const ct = res.headers.get('content-type') || ''
    if (!ct.includes('application/json')) {
      throw new Error('网络验证中，请稍等几秒后重试')
    }
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '注册失败')
    return data
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  const isLoggedIn = () => !!token.value
  const isAdmin = () => user.value?.role === 'admin'

  return { token, user, login, register, logout, authHeaders, isLoggedIn, isAdmin }
})
