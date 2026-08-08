<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

const goToMap = () => {
  router.push('/map')
}
</script>

<template>
  <button class="inline-globe" @click="goToMap" title="查看服务器分布">
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
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 50%;
  padding: 0;
  cursor: pointer;
  vertical-align: -3px;
  margin-left: 6px;
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
  inset: 2px;
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

/* Dual pulsing ripple rings */
.globe-ring {
  position: absolute;
  border-radius: 50%;
  border: 1.5px solid rgba(0, 255, 255, 0.7);
  pointer-events: none;
}

.ring-1 {
  inset: -3px;
  animation: ringPulse 2.5s ease-out infinite;
}

.ring-2 {
  inset: -3px;
  border-color: rgba(124, 58, 237, 0.6);
  animation: ringPulse 2.5s ease-out infinite 1.25s;
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

@keyframes orbit {
  from { transform: rotate(0deg) translateX(16px) rotate(0deg); }
  to { transform: rotate(360deg) translateX(16px) rotate(-360deg); }
}
</style>
