<script setup>
import { useRouter } from 'vue-router'
import { computed } from 'vue'

const props = defineProps({
  // 默认可点击跳转地图;登录页等场景传 clickable=false 只展示动画
  clickable: { type: Boolean, default: true },
  // 尺寸(px),默认 26;登录页传更大值
  size: { type: Number, default: 26 }
})

const router = useRouter()

const goToMap = () => {
  if (props.clickable) router.push('/map')
}

// 动态尺寸:地球本体按比例缩放
const globeStyle = computed(() => ({
  width: props.size + 'px',
  height: props.size + 'px',
  marginLeft: (props.size * 0.23) + 'px',
  verticalAlign: -(props.size * 0.12) + 'px'
}))
</script>

<template>
  <button class="inline-globe" :style="globeStyle" @click="goToMap" title="查看服务器分布">
    <span class="globe-glow"></span>
    <span class="globe-sphere">
      <span class="globe-lines"></span>
      <span class="globe-shine"></span>
    </span>
    <span class="globe-ring ring-1"></span>
    <span class="globe-ring ring-2"></span>
    <span class="globe-satellite"></span>
  </button>
</template>

<style scoped>
.inline-globe {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  padding: 0;
  cursor: pointer;
  background: radial-gradient(circle at 35% 30%, #2e6db8, #0a1230 75%);
  box-shadow:
    0 0 12px rgba(0, 255, 255, 0.35),
    0 0 24px rgba(124, 58, 237, 0.25),
    inset -3px -3px 8px rgba(0, 0, 0, 0.5);
  transition: transform 0.3s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.3s ease;
  position: relative;
  animation: floatGlobe 3s ease-in-out infinite;
}

.inline-globe:hover {
  transform: scale(1.2) rotate(8deg);
  box-shadow:
    0 0 18px rgba(0, 255, 255, 0.6),
    0 0 36px rgba(124, 58, 237, 0.45),
    inset -3px -3px 8px rgba(0, 0, 0, 0.5);
  animation-play-state: paused;
}

.inline-globe:active {
  transform: scale(0.92);
}

/* Soft ambient glow behind the globe */
.globe-glow {
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(0, 200, 255, 0.35) 0%, rgba(124, 58, 237, 0.18) 45%, transparent 70%);
  filter: blur(2px);
  pointer-events: none;
  animation: glowPulse 2.5s ease-in-out infinite;
}

.globe-sphere {
  position: absolute;
  inset: 8%;
  border-radius: 50%;
  overflow: hidden;
  background: radial-gradient(circle at 35% 30%, #3d7bd9, #0d1538 75%);
  box-shadow: inset -4px -3px 10px rgba(0, 0, 0, 0.6);
}

/* Rotating latitude/longitude grid (cyan neon) */
.globe-lines {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background:
    radial-gradient(ellipse at center, transparent 40%, rgba(0, 255, 255, 0.65) 40.5%, transparent 41%),
    radial-gradient(ellipse at center, transparent 62%, rgba(0, 255, 255, 0.5) 62.5%, transparent 63%),
    radial-gradient(ellipse at center, transparent 20%, rgba(0, 255, 255, 0.6) 20.5%, transparent 21%),
    linear-gradient(90deg, transparent 48%, rgba(0, 255, 255, 0.6) 48.5%, transparent 49.5%),
    linear-gradient(90deg, transparent 68%, rgba(0, 255, 255, 0.45) 68.5%, transparent 69.5%),
    linear-gradient(90deg, transparent 28%, rgba(0, 255, 255, 0.45) 28.5%, transparent 29.5%);
  animation: spin 8s linear infinite;
}

/* Moving light sweep across the surface */
.globe-shine {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: linear-gradient(115deg,
    transparent 0%,
    transparent 38%,
    rgba(255, 255, 255, 0.22) 46%,
    rgba(0, 255, 255, 0.15) 52%,
    transparent 62%,
    transparent 100%);
  animation: shineSweep 4.5s ease-in-out infinite;
}

/* ── 涟漪环(原版 border 样式 + 每 2 秒切换一种颜色) ── */
.globe-ring {
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  border: 1.5px solid rgba(0, 255, 255, 0.7);
  pointer-events: none;
}

/* 两个环:原版扩散动画 + 七色循环(14s 循环 = 每色 2s) */
.ring-1 {
  animation:
    ringPulse 2.5s ease-out infinite,
    colorCycle 14s linear infinite;
}

.ring-2 {
  animation:
    ringPulse 2.5s ease-out infinite 1.25s,
    colorCycle 14s linear infinite;
}

/* Tiny satellite dot orbiting the globe */
.globe-satellite {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #00ffff;
  box-shadow: 0 0 6px #00ffff, 0 0 12px rgba(0, 255, 255, 0.8);
  animation: orbit 4s linear infinite;
  pointer-events: none;
  margin: -2px 0 0 -2px;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes floatGlobe {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}

@keyframes glowPulse {
  0%, 100% { opacity: 0.6; transform: scale(0.95); }
  50% { opacity: 1; transform: scale(1.05); }
}

@keyframes shineSweep {
  0% { transform: rotate(0deg); opacity: 0.4; }
  50% { transform: rotate(180deg); opacity: 1; }
  100% { transform: rotate(360deg); opacity: 0.4; }
}

/* 涟漪扩散(原版动画):scale 放大 + 淡出 */
@keyframes ringPulse {
  0% {
    transform: scale(0.85);
    opacity: 0.9;
  }
  100% {
    transform: scale(1.5);
    opacity: 0;
  }
}

/* 七色循环:每 2 秒切换一种颜色,14s 一个完整循环 */
@keyframes colorCycle {
  0%, 14.28%   { border-color: #ff3b30; }  /* 红 */
  14.29%, 28.57% { border-color: #ff9500; }  /* 橙 */
  28.58%, 42.85% { border-color: #ffcc00; }  /* 黄 */
  42.86%, 57.14% { border-color: #34c759; }  /* 绿 */
  57.15%, 71.42% { border-color: #00c7be; }  /* 青 */
  71.43%, 85.71% { border-color: #007aff; }  /* 蓝 */
  85.72%, 100%   { border-color: #af52de; }  /* 紫 */
}

@keyframes orbit {
  from { transform: rotate(0deg) translateX(16px) rotate(0deg); }
  to { transform: rotate(360deg) translateX(16px) rotate(-360deg); }
}
</style>
