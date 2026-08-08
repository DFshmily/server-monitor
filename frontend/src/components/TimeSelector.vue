<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: 'realtime'
  }
})

const emit = defineEmits(['update:modelValue'])

const options = [
  { value: 'realtime', label: '实时' },
  { value: '1min', label: '1分钟' },
  { value: '5min', label: '5分钟' },
  { value: '1hour', label: '1小时' },
  { value: '1day', label: '1天' },
  { value: '1week', label: '1周' }
]

const isOpen = ref(false)

const selectedLabel = () => {
  const opt = options.find(o => o.value === props.modelValue)
  return opt ? opt.label : '实时'
}

const select = (value) => {
  emit('update:modelValue', value)
  isOpen.value = false
}

const toggle = () => {
  isOpen.value = !isOpen.value
}

const close = () => {
  isOpen.value = false
}
</script>

<template>
  <div class="time-selector" @click.stop>
    <button class="selector-button" @click="toggle">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <polyline points="12 6 12 12 16 14"/>
      </svg>
      <span>{{ selectedLabel() }}</span>
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" :class="{ rotated: isOpen }">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </button>
    <div v-if="isOpen" class="selector-dropdown">
      <div
        v-for="option in options"
        :key="option.value"
        class="selector-option"
        :class="{ selected: modelValue === option.value }"
        @click="select(option.value)"
      >
        {{ option.label }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.time-selector {
  position: relative;
}

.selector-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(0, 0, 0, 0.06);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.selector-button:hover {
  background: rgba(255, 255, 255, 0.95);
  color: var(--purple-600);
}

.selector-button svg.rotated {
  transform: rotate(180deg);
}

.selector-button svg {
  transition: transform 0.2s ease;
}

.selector-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 120px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
  padding: 4px;
  z-index: 100;
}

.selector-option {
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.selector-option:hover {
  background: var(--purple-50);
  color: var(--purple-600);
}

.selector-option.selected {
  background: var(--purple-100);
  color: var(--purple-700);
  font-weight: 600;
}
</style>
