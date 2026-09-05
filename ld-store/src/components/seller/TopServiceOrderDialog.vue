<template>
  <span ref="anchor" hidden></span>
  <Teleport :to="portalTarget || 'body'" :disabled="!portalTarget">
  <Transition name="service-dialog">
    <div v-if="open" class="service-dialog-layer top-service-theme" @click.self="$emit('close')">
      <section ref="panel" class="service-dialog-panel" role="dialog" aria-modal="true" aria-labelledby="top-service-detail-title" tabindex="-1" @keydown="handleKeydown">
        <header class="dialog-heading">
          <h2 id="top-service-detail-title">推广订单详情</h2>
          <button ref="closeButton" type="button" aria-label="关闭订单详情" @click="$emit('close')"><X :size="20" aria-hidden="true" /></button>
        </header>
        <div class="dialog-content"><slot /></div>
      </section>
    </div>
  </Transition>
  </Teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { X } from '@lucide/vue'
import '@/styles/top-service.css'
const props = defineProps({ open: Boolean, returnFocus: { type: Object, default: null } })
const emit = defineEmits(['close'])
const panel = ref(null)
const closeButton = ref(null)
const anchor = ref(null)
const portalTarget = shallowRef(null)
// Escape the routed page's isolated stacking context, retaining seller theme tokens.
onMounted(() => { portalTarget.value = anchor.value.closest('.seller-shell') || document.body })
let origin = null
let locked = false
let previousOverflow = ''
let previousPadding = ''

function handleKeydown(event) {
  // Cancellation confirmation is a separate, higher modal; its keys stay there.
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); emit('close'); return }
  if (event.key !== 'Tab') return
  const controls = [...panel.value.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), summary, [tabindex]:not([tabindex="-1"])')]
    .filter(el => !el.closest('[inert], [hidden]'))
  const first = controls[0]
  const last = controls.at(-1)
  if (!first) { event.preventDefault(); panel.value.focus(); return }
  if (!controls.includes(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus() }
  else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}

function release() {
  if (!locked) return
  locked = false
  document.body.style.overflow = previousOverflow
  document.body.style.paddingRight = previousPadding
  const target = origin
  origin = null
  void nextTick(() => {
    if (props.open) return
    if (target?.isConnected && !target.disabled && !target.closest('[inert]')) target.focus({ preventScroll: true })
    else document.getElementById('merchant-tab-orders')?.focus({ preventScroll: true })
  })
}

watch([() => props.open, portalTarget], async ([open, target]) => {
  if (!open) { release(); return }
  if (!target) return
  origin = props.returnFocus || document.activeElement
  previousOverflow = document.body.style.overflow
  previousPadding = document.body.style.paddingRight
  const scrollbar = window.innerWidth - document.documentElement.clientWidth
  if (scrollbar > 0 && scrollbar < 50) document.body.style.paddingRight = `${parseFloat(getComputedStyle(document.body).paddingRight || '0') + scrollbar}px`
  document.body.style.overflow = 'hidden'
  locked = true
  await nextTick()
  if (props.open) closeButton.value?.focus({ preventScroll: true })
}, { immediate: true, flush: 'post' })
onBeforeUnmount(release)
</script>

<style scoped>
.service-dialog-layer { position:fixed; inset:0; z-index:1400; display:grid; place-items:center; padding:24px; background:var(--palette-rgba-16-28-42-p55); backdrop-filter:blur(4px); }
.service-dialog-panel { display:flex; flex-direction:column; min-height:0; width:min(600px,100%); max-height:min(760px,calc(100dvh - 48px)); border:1px solid var(--seller-border); border-radius:18px; background:var(--seller-surface-strong); color:var(--seller-ink); box-shadow:0 24px 80px var(--palette-rgba-0-0-0-p22); outline:0; }
.dialog-heading { display:flex; align-items:center; justify-content:space-between; flex:0 0 auto; gap:18px; padding:12px 22px; border-bottom:1px solid var(--seller-border); }
.dialog-heading h2 { margin:0; font-family:"Noto Serif SC","Songti SC",serif; color:var(--seller-ink); font-size:21px; font-weight:600; }
.dialog-heading button { display:grid; place-items:center; width:44px; height:44px; flex:0 0 auto; border:1px solid var(--seller-border); border-radius:50%; color:var(--seller-muted); background:var(--seller-surface); }
.dialog-heading button:hover { color:var(--service-rose-ink); background:var(--service-rose-soft); border-color:var(--service-rose); }
.dialog-content { display:flex; flex-direction:column; min-height:0; padding:18px 22px; overflow:hidden; border-radius:0 0 18px 18px; }
.service-dialog-enter-active,.service-dialog-leave-active { transition:opacity .18s ease; }
.service-dialog-enter-active .service-dialog-panel,.service-dialog-leave-active .service-dialog-panel { transition:transform .18s ease; }
.service-dialog-enter-from,.service-dialog-leave-to { opacity:0; }
.service-dialog-enter-from .service-dialog-panel,.service-dialog-leave-to .service-dialog-panel { transform:translateY(10px); }
@media(max-width:640px) { .service-dialog-layer { padding:12px; padding-top:max(12px,env(safe-area-inset-top,0px)); padding-bottom:max(12px,env(safe-area-inset-bottom,0px)); } .service-dialog-panel { max-height:calc(100dvh - max(12px,env(safe-area-inset-top,0px)) - max(12px,env(safe-area-inset-bottom,0px))); border-radius:16px; } .dialog-heading { padding:10px 16px; } .dialog-heading h2 { font-size:20px; } .dialog-content { padding:16px; } }
@media(max-height:520px) and (min-width:641px) { .service-dialog-layer { padding:12px; } .service-dialog-panel { max-height:calc(100dvh - 24px); } .dialog-heading { padding:6px 18px; } .dialog-content { padding:12px 18px; } }
@media(prefers-reduced-motion:reduce) { .service-dialog-enter-active,.service-dialog-leave-active,.service-dialog-enter-active .service-dialog-panel,.service-dialog-leave-active .service-dialog-panel { transition:none; } }
</style>
