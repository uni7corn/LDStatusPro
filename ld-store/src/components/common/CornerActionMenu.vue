<template>
  <div
    ref="menuRef"
    class="corner-menu"
    :class="{ 'is-open': isOpen, 'is-visible': showMenu }"
    @keydown.esc.stop.prevent="closeMenuWithFocus"
    @focusout="handleFocusOut"
  >
    <button
      ref="triggerRef"
      type="button"
      class="corner-fab"
      @click.stop="toggleMenu"
      :aria-expanded="String(isOpen)"
      aria-label="快捷菜单"
    >
      <span class="fab-label">功能按钮</span>
      <span class="fab-glow" aria-hidden="true"></span>
      <svg class="fab-icon" :class="{ 'is-open': isOpen }" viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M12 4v6M12 14v6M4 12h6M14 12h6"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
        />
        <circle cx="12" cy="12" r="2.5" fill="currentColor" />
      </svg>
    </button>

    <button
      type="button"
      :inert="!isOpen || !showMenu ? '' : undefined"
      class="corner-action action-doodle"
      :class="{ 'is-active': isEnabled }"
      :style="actionStyle(0)"
      @click.stop="toggleDoodle"
      :title="isEnabled ? '关闭涂鸦背景' : '开启涂鸦背景'"
      :aria-label="isEnabled ? '关闭涂鸦背景' : '开启涂鸦背景'"
    >
      <svg
        class="action-icon"
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M12 19l7-7 3 3-7 7-3-3z"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <path
          d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <path
          d="M2 2l7.586 7.586"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <circle
          cx="11"
          cy="11"
          r="2"
          stroke="currentColor"
          stroke-width="1.5"
        />
      </svg>
      <span class="action-label">
        {{ isEnabled ? '关闭涂鸦背景' : '开启涂鸦背景' }}
      </span>
    </button>

    <button
      type="button"
      :inert="!isOpen || !showMenu ? '' : undefined"
      class="corner-action action-support"
      :style="actionStyle(1)"
      @click.stop="openSupport"
      title="支持LD士多"
      aria-label="支持LD士多"
    >
      <svg
        class="action-icon"
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M12 21l-1.4-1.3C5.4 15.4 2 12.3 2 8.5 2 5.4 4.4 3 7.5 3c1.7 0 3.4.8 4.5 2.1C13.1 3.8 14.8 3 16.5 3 19.6 3 22 5.4 22 8.5c0 3.8-3.4 6.9-8.6 11.5L12 21z"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <span class="action-label">支持LD士多</span>
    </button>

    <button
      type="button"
      :inert="!isOpen || !showMenu ? '' : undefined"
      class="corner-action action-merchant"
      :style="actionStyle(2)"
      @click.stop="openMerchantServices"
      title="卖家后台"
      aria-label="卖家后台"
    >
      <svg
        class="action-icon"
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M5 10l2-5h10l2 5"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <path
          d="M4 10h16v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8z"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linejoin="round"
        />
        <path
          d="M9 14h6"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
        />
      </svg>
      <span class="action-label">卖家后台</span>
    </button>

    <router-link
      to="/announcements"
      :inert="!isOpen || !showMenu ? '' : undefined"
      class="corner-action action-announcements"
      :style="actionStyle(3)"
      @click.stop="isOpen = false"
      title="公告中心"
      aria-label="公告中心"
    >
      <Megaphone class="action-icon" :size="20" :stroke-width="1.5" aria-hidden="true" />
      <span class="action-label">公告中心</span>
    </router-link>

    <Transition name="backtop-fade">
      <button
        v-if="showBackToTop"
        class="backtop-button"
        :class="{ 'is-shifted': isOpen }"
        @click.stop="scrollToTop"
        title="快速回顶"
        aria-label="快速回顶"
      >
        <svg class="backtop-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 17V7"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
          />
          <path
            d="M7.5 11.5L12 7l4.5 4.5"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </Transition>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { Megaphone } from '@lucide/vue'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:modelValue'])

const router = useRouter()
const route = useRoute()
const menuRef = ref(null)
const triggerRef = ref(null)
let revealTimer
const showMenu = ref(false)
const isOpen = ref(false)
const isEnabled = ref(props.modelValue)
const showBackToTop = ref(false)

const radius = 116
const positions = [
  { x: 0, y: radius },
  { x: radius * 0.5, y: radius * 0.866 },
  { x: radius * 0.866, y: radius * 0.5 },
  { x: radius, y: 0 }
]

const actionStyle = (index) => {
  const { x, y } = positions[index]
  if (!isOpen.value) {
    return {
      transform: 'translate(0, 0) scale(0.6)',
      opacity: 0,
      transitionDelay: '0s',
      transitionTimingFunction: 'cubic-bezier(0.4, 0, 0.2, 1)'
    }
  }
  return {
    transform: `translate(${-x}px, ${-y}px) scale(1)`,
    opacity: 1,
    transitionDelay: `${index * 0.06}s`,
    transitionTimingFunction: 'cubic-bezier(0.22, 1, 0.36, 1)'
  }
}

function toggleMenu() {
  isOpen.value = !isOpen.value
}

function closeMenuWithFocus() {
  isOpen.value = false
  triggerRef.value?.focus()
}

function handleFocusOut(event) {
  if (!menuRef.value?.contains(event.relatedTarget)) isOpen.value = false
}

function toggleDoodle() {
  const next = !isEnabled.value
  isEnabled.value = next
  emit('update:modelValue', next)
  isOpen.value = false
}

function openSupport() {
  isOpen.value = false
  router.push('/support')
}

function openMerchantServices() {
  isOpen.value = false
  router.push('/seller')
}

function updateBackToTopVisibility() {
  showBackToTop.value = window.scrollY > 280
}

function handleScroll() {
  updateBackToTopVisibility()
}

function scrollToTop() {
  isOpen.value = false
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({
    top: 0,
    behavior: prefersReducedMotion ? 'auto' : 'smooth'
  })
}

function handleDocClick(event) {
  if (!isOpen.value) return
  const target = menuRef.value
  if (target && !target.contains(event.target)) {
    isOpen.value = false
  }
}

onMounted(() => {
  revealTimer = setTimeout(() => {
    showMenu.value = true
  }, 450)
  updateBackToTopVisibility()
  document.addEventListener('click', handleDocClick)
  window.addEventListener('scroll', handleScroll, { passive: true })
})

onUnmounted(() => {
  clearTimeout(revealTimer)
  document.removeEventListener('click', handleDocClick)
  window.removeEventListener('scroll', handleScroll)
})

watch(
  () => props.modelValue,
  (val) => {
    isEnabled.value = val
  }
)

watch(
  () => route.fullPath,
  () => {
    isOpen.value = false
    updateBackToTopVisibility()
  }
)
</script>

<style scoped>
.corner-menu {
  position: fixed;
  right: 20px;
  bottom: 80px;
  width: 190px;
  height: 190px;
  z-index: 120;
  pointer-events: none;
  --corner-action-bg: var(--glass-bg-light);
  --corner-action-border: var(--glass-border-light);
  --corner-action-shadow: 0 8px 16px var(--glass-shadow), inset 0 1px 0 var(--glass-shine);
  --corner-action-hover-shadow: 0 12px 24px var(--glass-shadow), inset 0 1px 0 var(--glass-shine);
  --corner-label-bg: var(--glass-bg-heavy);
  --corner-label-border: var(--glass-border);
  --corner-label-shadow: 0 6px 16px var(--glass-shadow);
  --corner-backtop-bg: var(--glass-bg-light);
  --corner-backtop-border: var(--glass-border-light);
  --corner-backtop-shadow: 0 10px 22px var(--glass-shadow), inset 0 1px 0 var(--glass-shine);
  --corner-backtop-hover-shadow: 0 14px 28px var(--palette-rgba-15-23-42-0p16), inset 0 1px 0 var(--palette-rgba-255-255-255-0p35);
  --corner-fab-bg: linear-gradient(
    145deg,
    color-mix(in srgb, var(--color-primary) 75%, var(--palette-hex-ffffff)) 0%,
    color-mix(in srgb, var(--color-primary) 85%, var(--palette-hex-7e6e5f)) 100%
  );
  --corner-fab-shadow: var(--shadow-primary), 0 12px 26px var(--palette-rgba-159-143-125-0p28);
  --corner-fab-border: var(--palette-rgba-255-255-255-0p55);
  --corner-fab-hover-shadow: 0 10px 24px var(--palette-rgba-159-143-125-0p35), 0 0 0 6px var(--palette-rgba-181-168-152-0p08);
  --corner-fab-open-shadow: 0 12px 26px var(--palette-rgba-159-143-125-0p35), 0 0 0 8px var(--palette-rgba-181-168-152-0p12);
  --corner-fab-sparkle:
    radial-gradient(circle at 30% 30%, var(--palette-rgba-255-255-255-0p45) 0 2px, transparent 3px),
    radial-gradient(circle at 70% 40%, var(--palette-rgba-255-255-255-0p35) 0 1.5px, transparent 3px),
    radial-gradient(circle at 45% 70%, var(--palette-rgba-255-255-255-0p3) 0 1.8px, transparent 3px);
  --corner-fab-dash: var(--palette-rgba-255-255-255-0p35);
  --corner-fab-glow: radial-gradient(circle, var(--palette-rgba-255-255-255-0p4), transparent 60%);
  --corner-doodle-bg: linear-gradient(135deg, var(--palette-rgba-181-168-152-0p2), var(--palette-rgba-255-255-255-0p9));
  --corner-doodle-active-bg: var(--color-primary-light);
  --corner-support-color: var(--palette-hex-ef7a7a);
  --corner-support-border: color-mix(in srgb, var(--palette-hex-ef7a7a) 40%, transparent);
  --corner-support-bg: linear-gradient(135deg, var(--palette-rgba-239-122-122-0p2), var(--palette-rgba-255-255-255-0p9));
  --corner-support-hover-color: var(--palette-hex-e65a5a);
  --corner-support-hover-shadow: 0 12px 24px var(--palette-rgba-239-122-122-0p25), inset 0 1px 0 var(--palette-rgba-255-255-255-0p4);
  --corner-merchant-color: var(--palette-hex-9b6a11);
  --corner-merchant-border: color-mix(in srgb, var(--palette-hex-c48a22) 45%, transparent);
  --corner-merchant-bg: linear-gradient(135deg, var(--palette-rgba-196-138-34-0p22), var(--palette-rgba-255-248-230-0p95));
  --corner-merchant-hover-color: var(--palette-hex-7a4f08);
  --corner-merchant-hover-shadow: 0 12px 24px var(--palette-rgba-196-138-34-0p24), inset 0 1px 0 var(--palette-rgba-255-255-255-0p45);
  opacity: 0;
  transform: translateY(18px) scale(0.96);
  transition: opacity 0.3s ease, transform 0.3s ease;
}

:global(html.dark .corner-menu) {
  --corner-action-bg: var(--palette-rgba-40-34-29-0p94);
  --corner-action-border: var(--palette-rgba-255-232-205-0p12);
  --corner-action-shadow: 0 12px 22px var(--palette-rgba-0-0-0-0p28), inset 0 1px 0 var(--palette-rgba-255-240-214-0p06);
  --corner-action-hover-shadow: 0 16px 28px var(--palette-rgba-0-0-0-0p34), inset 0 1px 0 var(--palette-rgba-255-240-214-0p1);
  --corner-label-bg: var(--palette-rgba-36-30-26-0p98);
  --corner-label-border: var(--palette-rgba-255-232-205-0p12);
  --corner-label-shadow: 0 10px 24px var(--palette-rgba-0-0-0-0p3);
  --corner-backtop-bg: var(--palette-rgba-40-34-29-0p96);
  --corner-backtop-border: var(--palette-rgba-255-232-205-0p12);
  --corner-backtop-shadow: 0 12px 24px var(--palette-rgba-0-0-0-0p3), inset 0 1px 0 var(--palette-rgba-255-240-214-0p08);
  --corner-backtop-hover-shadow: 0 16px 30px var(--palette-rgba-0-0-0-0p34), inset 0 1px 0 var(--palette-rgba-255-240-214-0p1);
  --corner-fab-bg: linear-gradient(145deg, var(--palette-hex-e0b55f) 0%, var(--palette-hex-8d641b) 52%, var(--palette-hex-5c3c0f) 100%);
  --corner-fab-shadow: 0 14px 30px var(--palette-rgba-0-0-0-0p34), 0 0 0 1px var(--palette-rgba-255-240-214-0p1) inset;
  --corner-fab-border: var(--palette-rgba-255-240-214-0p18);
  --corner-fab-hover-shadow: 0 16px 30px var(--palette-rgba-0-0-0-0p38), 0 0 0 6px var(--palette-rgba-244-201-109-0p12);
  --corner-fab-open-shadow: 0 18px 34px var(--palette-rgba-0-0-0-0p42), 0 0 0 8px var(--palette-rgba-244-201-109-0p16);
  --corner-fab-sparkle:
    radial-gradient(circle at 30% 30%, var(--palette-rgba-255-244-224-0p4) 0 2px, transparent 3px),
    radial-gradient(circle at 70% 40%, var(--palette-rgba-255-232-205-0p28) 0 1.5px, transparent 3px),
    radial-gradient(circle at 45% 70%, var(--palette-rgba-255-216-150-0p26) 0 1.8px, transparent 3px);
  --corner-fab-dash: var(--palette-rgba-255-240-214-0p26);
  --corner-fab-glow: radial-gradient(circle, var(--palette-rgba-255-221-145-0p28), transparent 60%);
  --corner-doodle-bg: linear-gradient(135deg, var(--palette-rgba-197-184-168-0p22), var(--palette-rgba-58-48-40-0p96));
  --corner-doodle-active-bg: var(--palette-rgba-74-64-55-0p96);
  --corner-support-color: var(--palette-hex-ff9aa6);
  --corner-support-border: var(--palette-rgba-248-113-113-0p28);
  --corner-support-bg: linear-gradient(135deg, var(--palette-rgba-248-113-113-0p2), var(--palette-rgba-64-35-37-0p96));
  --corner-support-hover-color: var(--palette-hex-ffc2ca);
  --corner-support-hover-shadow: 0 14px 26px var(--palette-rgba-127-29-29-0p28), inset 0 1px 0 var(--palette-rgba-255-226-231-0p08);
  --corner-merchant-color: var(--palette-hex-f0c978);
  --corner-merchant-border: var(--palette-rgba-244-201-109-0p26);
  --corner-merchant-bg: linear-gradient(135deg, var(--palette-rgba-216-163-60-0p24), var(--palette-rgba-78-56-22-0p96));
  --corner-merchant-hover-color: var(--palette-hex-ffe7b6);
  --corner-merchant-hover-shadow: 0 14px 26px var(--palette-rgba-104-66-10-0p28), inset 0 1px 0 var(--palette-rgba-255-240-214-0p1);
}

.corner-menu.is-visible {
  opacity: 1;
  transform: translateY(0) scale(1);
}

.corner-action {
  position: absolute;
  right: 6px;
  bottom: 6px;
  width: 46px;
  height: 46px;
  --label-shift-y: -55%;
  border-radius: 50%;
  background: var(--corner-action-bg);
  border: 1px solid var(--corner-action-border);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--corner-action-shadow);
  transition: transform 0.36s ease, opacity 0.22s ease, box-shadow 0.25s ease, color 0.25s ease, filter 0.2s ease;
  pointer-events: none;
}

.corner-menu.is-open .corner-action {
  pointer-events: auto;
}

.corner-action:hover {
  color: var(--color-primary);
  box-shadow: var(--corner-action-hover-shadow);
}

.corner-action:active {
  filter: brightness(0.98);
}

.corner-action.is-active {
  color: var(--color-primary);
  border-color: var(--color-primary);
  background: var(--corner-doodle-active-bg);
}

.action-doodle {
  --label-shift-y: -90%;
  background: var(--corner-doodle-bg);
  color: var(--text-secondary);
}

.action-support {
  --label-shift-y: -20%;
  color: var(--corner-support-color);
  border-color: var(--corner-support-border);
  background: var(--corner-support-bg);
}

.action-support:hover {
  color: var(--corner-support-hover-color);
  box-shadow: var(--corner-support-hover-shadow);
}

.action-merchant {
  --label-shift-y: 45%;
  color: var(--corner-merchant-color);
  border-color: var(--corner-merchant-border);
  background: var(--corner-merchant-bg);
}

.action-merchant:hover {
  color: var(--corner-merchant-hover-color);
  box-shadow: var(--corner-merchant-hover-shadow);
}

.action-announcements {
  color: var(--action-primary);
  background: var(--surface-paper-card);
  border-color: var(--border-default-semantic);
  text-decoration: none;
}

.corner-menu :focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 4px;
}

.action-label {
  position: absolute;
  right: 56px;
  top: 50%;
  transform: translateY(var(--label-shift-y)) translateX(8px);
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: var(--corner-label-bg);
  border: 1px solid var(--corner-label-border);
  color: var(--text-secondary);
  opacity: 0;
  white-space: nowrap;
  box-shadow: var(--corner-label-shadow);
  transition: opacity 0.2s ease, transform 0.2s ease;
  pointer-events: none;
}

.corner-action:hover .action-label,
.corner-action:focus-visible .action-label {
  opacity: 1;
  transform: translateY(var(--label-shift-y)) translateX(0);
}

.corner-fab {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--corner-fab-bg);
  color: var(--palette-hex-ffffff);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--corner-fab-shadow);
  border: 1px solid var(--corner-fab-border);
  overflow: hidden;
  transition: transform 0.25s ease, box-shadow 0.25s ease;
  pointer-events: auto;
  touch-action: manipulation;
}

.backtop-button {
  position: absolute;
  right: 4px;
  bottom: 68px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 1px solid var(--corner-backtop-border);
  background: var(--corner-backtop-bg);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--corner-backtop-shadow);
  transition: transform 0.28s ease, opacity 0.24s ease, box-shadow 0.24s ease, color 0.24s ease;
  pointer-events: auto;
  touch-action: manipulation;
}

.backtop-button:hover {
  color: var(--color-primary);
  transform: translateY(-2px);
  box-shadow: var(--corner-backtop-hover-shadow);
}

.backtop-button.is-shifted {
  transform: translateY(-128px);
}

.backtop-button.is-shifted:hover {
  transform: translateY(-130px);
}

.backtop-icon {
  width: 20px;
  height: 20px;
}

.backtop-fade-enter-active,
.backtop-fade-leave-active {
  transition: opacity 0.24s ease, transform 0.24s ease;
}

.backtop-fade-enter-from,
.backtop-fade-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.92);
}

.fab-label {
  position: absolute;
  right: 62px;
  top: 50%;
  transform: translateY(-50%) translateX(8px);
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: var(--corner-label-bg);
  border: 1px solid var(--corner-label-border);
  color: var(--text-secondary);
  opacity: 0;
  white-space: nowrap;
  box-shadow: var(--corner-label-shadow);
  transition: opacity 0.2s ease, transform 0.2s ease;
  pointer-events: none;
}

.corner-fab:hover .fab-label,
.corner-fab:focus-visible .fab-label {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
}

.corner-fab::before,
.corner-fab::after {
  content: '';
  position: absolute;
  inset: 6px;
  border-radius: 50%;
  pointer-events: none;
}

.corner-fab::before {
  background: var(--corner-fab-sparkle);
  opacity: 0.8;
}

.corner-fab::after {
  inset: 8px;
  border: 1px dashed var(--corner-fab-dash);
  opacity: 0.7;
}

.corner-fab:hover {
  transform: translateY(-1px);
  box-shadow: var(--corner-fab-hover-shadow);
}

.corner-menu.is-open .corner-fab {
  transform: translateY(-1px) scale(1.02);
  box-shadow: var(--corner-fab-open-shadow);
}

.corner-fab:active {
  transform: scale(0.96);
}

.fab-glow {
  position: absolute;
  inset: -20%;
  background: var(--corner-fab-glow);
  opacity: 0.8;
  animation: fab-pulse 3.2s ease-in-out infinite;
}

.fab-icon {
  width: 24px;
  height: 24px;
  stroke: currentColor;
  fill: none;
  transition: transform 0.3s ease;
}

.fab-icon.is-open {
  transform: rotate(45deg) scale(0.9);
}

@keyframes fab-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.7;
  }
  50% {
    transform: scale(1.1);
    opacity: 0.95;
  }
}

@media (max-width: 640px) {
  .corner-menu {
    right: 16px;
    bottom: 96px;
    width: 170px;
    height: 170px;
  }

  .corner-action {
    width: 44px;
    height: 44px;
  }

  .corner-fab {
    width: 48px;
    height: 48px;
  }

  .backtop-button {
    right: 2px;
    bottom: 62px;
    width: 44px;
    height: 44px;
  }

  .backtop-button.is-shifted {
    transform: translateY(-128px);
  }

  .backtop-button.is-shifted:hover {
    transform: translateY(-130px);
  }

  .action-label {
    font-size: 11px;
    padding: 3px 8px;
  }

  .fab-label {
    font-size: 11px;
    padding: 3px 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .corner-menu,
  .corner-action,
  .action-label,
  .corner-fab,
  .fab-icon,
  .backtop-button {
    transition: none;
  }

  .fab-glow {
    animation: none;
  }
}
</style>
