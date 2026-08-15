<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import FloatingGlobe from '../components/FloatingGlobe.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

// 模式: login | register
const mode = ref('login')

// 登录
const email = ref('')
const password = ref('')
const remember = ref(true)

// 注册步骤 1: 邮箱 + 邀请码
const regEmail = ref('')
const inviteCode = ref('')
// 注册步骤 2: 验证码 + 密码
const verifyCode = ref('')
const regPassword = ref('')
const confirmPassword = ref('')

const error = ref('')
const info = ref('')
const loading = ref(false)
const codeSent = ref(false)
const countdown = ref(0)
let countdownTimer = null

const pageTitle = computed(() => (mode.value === 'login' ? '欢迎回来' : '创建账号'))
const pageSub = computed(() => (mode.value === 'login' ? '登录以查看服务器详情' : '两步完成注册'))

async function handleLogin() {
  error.value = ''
  if (!email.value || !password.value) {
    error.value = '请输入邮箱和密码'
    return
  }
  loading.value = true
  try {
    await auth.login(email.value, password.value, remember.value)
    router.push(route.query.redirect || '/')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function sendCode() {
  error.value = ''
  info.value = ''
  if (!regEmail.value || !inviteCode.value) {
    error.value = '请先填写邮箱和邀请码'
    return
  }
  loading.value = true
  try {
    const res = await fetch('/api/auth/send-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: regEmail.value, invite_code: inviteCode.value })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '发送失败')
    codeSent.value = true
    info.value = data.message
    startCountdown(60)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function startCountdown(sec) {
  countdown.value = sec
  countdownTimer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) clearInterval(countdownTimer)
  }, 1000)
}

async function handleRegister() {
  error.value = ''
  if (!verifyCode.value || !regPassword.value || !confirmPassword.value) {
    error.value = '请填写验证码和密码'
    return
  }
  if (regPassword.value.length < 8) {
    error.value = '密码至少 8 位'
    return
  }
  if (regPassword.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        email: regEmail.value,
        invite_code: inviteCode.value,
        code: verifyCode.value,
        password: regPassword.value
      })
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '注册失败')
    mode.value = 'login'
    email.value = regEmail.value
    info.value = '🎉 注册成功，请登录'
    error.value = ''
    codeSent.value = false
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  error.value = ''
  info.value = ''
  codeSent.value = false
}

// ── 星光粒子背景 ──
const stars = ref([])
let starTimer = null

onMounted(() => {
  stars.value = Array.from({ length: 60 }, () => ({
    left: Math.random() * 100,
    top: Math.random() * 100,
    size: Math.random() * 2 + 1,
    delay: Math.random() * 4,
    duration: Math.random() * 3 + 2
  }))
})

onUnmounted(() => {
  if (countdownTimer) clearInterval(countdownTimer)
  if (starTimer) clearInterval(starTimer)
})
</script>

<template>
  <div class="auth-page">
    <!-- 星光背景 -->
    <div class="starfield">
      <span
        v-for="(s, i) in stars"
        :key="i"
        class="star"
        :style="{
          left: s.left + '%',
          top: s.top + '%',
          width: s.size + 'px',
          height: s.size + 'px',
          animationDelay: s.delay + 's',
          animationDuration: s.duration + 's'
        }"
      ></span>
    </div>
    <!-- 光晕 -->
    <div class="aurora aurora-1"></div>
    <div class="aurora aurora-2"></div>

    <div class="auth-card">
      <div class="auth-logo">
        <h1 class="auth-title">DFshmily の<FloatingGlobe :clickable="false" :size="34" /></h1>
        <p class="subtitle">{{ pageSub }}</p>
      </div>

      <!-- 登录模式 -->
      <!-- novalidate: 禁用浏览器内置校验(Safari 会弹英文 pattern 报错), 统一走应用层中文校验 -->
      <form v-if="mode === 'login'" class="auth-form" novalidate @submit.prevent="handleLogin">
        <div class="field">
          <label>邮箱</label>
          <div class="input-wrap">
            <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 7l9 6 9-6"/></svg>
            <input v-model="email" type="email" placeholder="your@email.com" autocomplete="email" />
          </div>
        </div>
        <div class="field">
          <label>密码</label>
          <div class="input-wrap">
            <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="3"/><path d="M8 11V7a4 4 0 018 0v4"/></svg>
            <input v-model="password" type="password" placeholder="••••••••" autocomplete="current-password" />
          </div>
        </div>
        <label class="remember">
          <input v-model="remember" type="checkbox" />
          <span class="checkmark"></span>
          <span>记住我（7 天免登录）</span>
        </label>
        <div v-if="error" class="error-msg">{{ error }}</div>
        <div v-if="info" class="info-msg">{{ info }}</div>
        <button type="submit" class="auth-btn" :disabled="loading">
          {{ loading ? '请稍候...' : '登 录' }}
        </button>
      </form>

      <!-- 注册模式 -->
      <form v-else class="auth-form" novalidate @submit.prevent="handleRegister">
        <div class="step-indicator">
          <span class="step-dot" :class="{ active: true }">1</span>
          <span class="step-line"></span>
          <span class="step-dot" :class="{ active: codeSent }">2</span>
          <div class="step-label">
            <span :class="{ on: !codeSent }">信息验证</span>
            <span :class="{ on: codeSent }">设置密码</span>
          </div>
        </div>

        <template v-if="!codeSent">
          <div class="field">
            <label>邮箱</label>
            <div class="input-wrap">
              <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 7l9 6 9-6"/></svg>
              <input v-model="regEmail" type="email" placeholder="your@email.com" autocomplete="email" />
            </div>
          </div>
          <div class="field">
            <label>邀请码</label>
            <div class="input-wrap">
              <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="3"/><path d="M7 11V7a5 5 0 0110 0v4"/><circle cx="12" cy="16" r="1.5"/></svg>
              <input v-model="inviteCode" type="text" placeholder="向管理员索取邀请码" autocomplete="off" />
            </div>
          </div>
          <div v-if="error" class="error-msg">{{ error }}</div>
          <button type="button" class="auth-btn" :disabled="loading" @click="sendCode">
            {{ loading ? '发送中...' : '获取邮箱验证码' }}
          </button>
        </template>

        <template v-else>
          <div class="field">
            <label>邮箱验证码</label>
            <div class="input-wrap">
              <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l2.5 5.5L20 9l-4 4 1 6-5-3-5 3 1-6-4-4 5.5-.5z"/></svg>
              <input v-model="verifyCode" type="text" placeholder="6 位验证码" maxlength="6" autocomplete="one-time-code" />
            </div>
            <button type="button" class="resend-btn" :disabled="countdown > 0" @click="sendCode">
              {{ countdown > 0 ? `${countdown}s 后重发` : '重新发送' }}
            </button>
          </div>
          <div class="field">
            <label>设置密码</label>
            <div class="input-wrap">
              <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="3"/><path d="M8 11V7a4 4 0 018 0v4"/></svg>
              <input v-model="regPassword" type="password" placeholder="至少 8 位" autocomplete="new-password" />
            </div>
          </div>
          <div class="field">
            <label>确认密码</label>
            <div class="input-wrap">
              <svg class="input-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
              <input v-model="confirmPassword" type="password" placeholder="再次输入密码" autocomplete="new-password" />
            </div>
          </div>
          <div v-if="error" class="error-msg">{{ error }}</div>
          <div v-if="info" class="info-msg">{{ info }}</div>
          <button type="submit" class="auth-btn" :disabled="loading">
            {{ loading ? '请稍候...' : '完成注册' }}
          </button>
        </template>
      </form>

      <div class="switch-line">
        <span class="switch-text">{{ mode === 'login' ? '还没有账号？' : '已有账号？' }}</span>
        <a @click="switchMode">
          {{ mode === 'login' ? '用邀请码注册' : '去登录' }}
        </a>
      </div>

      <div class="brand-line">Server Monitor · 自建监控面板</div>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  position: relative;
  overflow: hidden;
  background: linear-gradient(160deg, #0b1026 0%, #141b3d 45%, #1e1440 100%);
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', 'Segoe UI', sans-serif;
}

/* ── 星光粒子 ── */
.starfield {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.star {
  position: absolute;
  border-radius: 50%;
  background: #fff;
  opacity: 0;
  animation: twinkle ease-in-out infinite;
}

@keyframes twinkle {
  0%, 100% { opacity: 0; }
  50% { opacity: 0.9; }
}

/* ── 极光光晕 ── */
.aurora {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
  opacity: 0.45;
}

.aurora-1 {
  width: 420px;
  height: 420px;
  top: -120px;
  right: -100px;
  background: radial-gradient(circle, rgba(124, 58, 237, 0.5), transparent 70%);
  animation: drift1 12s ease-in-out infinite;
}

.aurora-2 {
  width: 380px;
  height: 380px;
  bottom: -140px;
  left: -80px;
  background: radial-gradient(circle, rgba(0, 199, 190, 0.35), transparent 70%);
  animation: drift2 14s ease-in-out infinite;
}

@keyframes drift1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(-30px, 20px) scale(1.1); }
}

@keyframes drift2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(24px, -18px) scale(1.08); }
}

/* ── 卡片 ── */
.auth-card {
  width: 100%;
  max-width: 400px;
  padding: 44px 36px;
  border-radius: 28px;
  position: relative;
  z-index: 10;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(24px) saturate(1.4);
  -webkit-backdrop-filter: blur(24px) saturate(1.4);
  box-shadow:
    0 24px 80px rgba(0, 0, 0, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
  animation: cardIn 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}

/* 顶部渐变光条 */
.auth-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 12%;
  right: 12%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(167, 139, 250, 0.9), rgba(125, 211, 252, 0.9), transparent);
  border-radius: 50%;
  box-shadow: 0 0 12px rgba(167, 139, 250, 0.5);
}

@keyframes cardIn {
  from { transform: translateY(28px) scale(0.97); opacity: 0; }
  to { transform: translateY(0) scale(1); opacity: 1; }
}

/* ── Logo 区 ── */
.auth-logo {
  text-align: center;
  margin-bottom: 32px;
}

.auth-title {
  font-size: 26px;
  font-weight: 700;
  margin: 0 0 10px;
  letter-spacing: 2px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  /* 渐变文字 */
  background: linear-gradient(90deg, #ffffff 0%, #e9d5ff 45%, #bae6fd 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  filter: drop-shadow(0 2px 16px rgba(139, 92, 246, 0.35));
}

.auth-title :deep(.inline-globe) {
  margin-left: 2px;
}

.subtitle {
  color: rgba(255, 255, 255, 0.5);
  font-size: 14px;
  margin: 0;
}

/* ── 表单 ── */
.auth-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: relative;
}

.field label {
  font-size: 13px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.7);
  letter-spacing: 0.3px;
}

.input-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.1);
  transition: all 0.25s ease;
}

.input-wrap:focus-within {
  border-color: rgba(167, 139, 250, 0.65);
  background: rgba(255, 255, 255, 0.1);
  box-shadow: 0 0 0 4px rgba(139, 92, 246, 0.15), 0 0 24px rgba(139, 92, 246, 0.15);
}

.input-wrap:focus-within .input-icon {
  color: #a78bfa;
  filter: drop-shadow(0 0 6px rgba(167, 139, 250, 0.6));
  transition: all 0.25s ease;
}

.input-icon {
  width: 17px;
  height: 17px;
  color: rgba(255, 255, 255, 0.45);
  flex-shrink: 0;
}

.input-wrap input {
  flex: 1;
  padding: 14px 0;
  border: none;
  background: transparent;
  color: #fff;
  font-size: 15px;
  outline: none;
}

.input-wrap input::placeholder {
  color: rgba(255, 255, 255, 0.3);
}

/* 验证码重发按钮 */
.resend-btn {
  position: absolute;
  right: 12px;
  bottom: 12px;
  padding: 6px 12px;
  border: 1px solid rgba(139, 92, 246, 0.4);
  border-radius: 10px;
  background: rgba(139, 92, 246, 0.12);
  color: #c4b5fd;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  z-index: 2;
}

.resend-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.resend-btn:not(:disabled):hover {
  background: rgba(139, 92, 246, 0.25);
}

/* 记住我 */
.remember {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  user-select: none;
}

.remember input {
  display: none;
}

.checkmark {
  width: 18px;
  height: 18px;
  border-radius: 6px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  position: relative;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.remember input:checked + .checkmark {
  background: linear-gradient(135deg, var(--purple-500, #8b5cf6), var(--purple-700, #6d28d9));
  border-color: transparent;
}

.remember input:checked + .checkmark::after {
  content: '';
  position: absolute;
  left: 5px;
  top: 1px;
  width: 5px;
  height: 10px;
  border: solid #fff;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}

/* 提示条 */
.error-msg {
  background: rgba(255, 59, 48, 0.15);
  border: 1px solid rgba(255, 59, 48, 0.3);
  color: #ff9d95;
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 13px;
  animation: shake 0.4s ease;
}

.info-msg {
  background: rgba(52, 199, 89, 0.12);
  border: 1px solid rgba(52, 199, 89, 0.3);
  color: #8ee6a5;
  padding: 12px 14px;
  border-radius: 12px;
  font-size: 13px;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}

/* 按钮 */
.auth-btn {
  margin-top: 6px;
  padding: 15px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 40%, #6d28d9 100%);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 3px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: all 0.25s ease;
  box-shadow: 0 8px 24px rgba(124, 58, 237, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

/* 扫光动画 */
.auth-btn::after {
  content: '';
  position: absolute;
  top: 0;
  left: -80%;
  width: 60%;
  height: 100%;
  background: linear-gradient(105deg, transparent, rgba(255, 255, 255, 0.25), transparent);
  transform: skewX(-20deg);
  animation: btnShine 3.2s ease-in-out infinite;
}

@keyframes btnShine {
  0% { left: -80%; }
  55% { left: 130%; }
  100% { left: 130%; }
}

.auth-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(124, 58, 237, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.auth-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.98);
}

.auth-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  animation: none;
}

.auth-btn:disabled::after {
  animation: none;
}

/* 步骤指示器 */
.step-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 6px;
  position: relative;
}

.step-dot {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.4);
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;
  z-index: 1;
}

.step-dot.active {
  background: linear-gradient(135deg, #8b5cf6, #6d28d9);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 0 16px rgba(139, 92, 246, 0.5);
}

.step-line {
  width: 44px;
  height: 2px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
}

.step-label {
  position: absolute;
  top: 34px;
  display: flex;
  gap: 64px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
}

.step-label span { transition: color 0.3s; }
.step-label span.on { color: #c4b5fd; }

/* 切换登录/注册 */
.switch-line {
  text-align: center;
  margin-top: 24px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.65);
}

.switch-line a {
  color: #c4b5fd;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  transition: all 0.2s;
  background-image: linear-gradient(90deg, #a78bfa, #7dd3fc);
  background-size: 0% 1.5px;
  background-repeat: no-repeat;
  background-position: left bottom;
  padding-bottom: 2px;
}

.switch-line a:hover {
  color: #fff;
  background-size: 100% 1.5px;
  text-shadow: 0 0 12px rgba(139, 92, 246, 0.6);
}

/* 底部品牌行 */
.brand-line {
  margin-top: 22px;
  text-align: center;
  font-size: 11px;
  letter-spacing: 2px;
  color: rgba(255, 255, 255, 0.25);
  font-weight: 500;
}

/* 响应式 */
@media (max-width: 480px) {
  .auth-card { padding: 32px 20px; }
  .auth-title { font-size: 22px; }
  .step-label { gap: 48px; }
}
</style>
