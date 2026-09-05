<template>
  <ol class="refund-stages" aria-label="退款处理阶段">
    <li
      v-for="(stage, index) in stages"
      :key="stage.key"
      :class="[`is-${stage.state}`, `tone-${stage.tone}`]"
      :aria-current="stage.current ? 'step' : undefined"
    >
      <span class="refund-stage__marker" aria-hidden="true">
        <Check v-if="stage.state === 'done'" :size="14" :stroke-width="2.5" />
        <TriangleAlert v-else-if="stage.state === 'error'" :size="14" :stroke-width="2.3" />
        <Minus v-else-if="stage.state === 'skipped'" :size="14" :stroke-width="2.3" />
        <span v-else>{{ index + 1 }}</span>
      </span>
      <span class="refund-stage__copy">
        <strong>{{ stage.label }}</strong>
        <small>{{ stage.description }}</small>
        <span class="refund-stage__sr-only">，{{ getStageStateLabel(stage) }}</span>
      </span>
    </li>
  </ol>
</template>

<script setup>
import { Check, Minus, TriangleAlert } from '@lucide/vue'

defineProps({
  stages: { type: Array, required: true }
})

function getStageStateLabel(stage) {
  if (stage.state === 'done') return stage.current ? '当前结果，已完成' : '已完成'
  if (stage.state === 'current') return '当前阶段'
  if (stage.state === 'error') return '当前阶段，需要处理'
  if (stage.state === 'skipped') return '已跳过'
  return '尚未开始'
}
</script>

<style scoped>
.refund-stages {
  --stage-success: var(--color-success, var(--palette-hex-3f7a52));
  --stage-info: var(--color-info, var(--palette-hex-277da1));
  --stage-warning: var(--color-warning, var(--palette-hex-a66b24));
  --stage-danger: var(--color-danger, var(--palette-hex-b54a4a));
  --stage-brand: var(--color-primary-hover, var(--color-primary));
  display: grid;
  gap: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

.refund-stages li {
  position: relative;
  min-width: 0;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 12px;
  padding: 0 0 20px;
  color: var(--text-tertiary);
}

.refund-stages li:not(:last-child)::after {
  content: '';
  position: absolute;
  z-index: 0;
  top: 30px;
  bottom: 0;
  left: 14px;
  width: 2px;
  border-radius: 999px;
  background: var(--border-medium);
}

.refund-stages li.is-done:not(:last-child)::after {
  background: var(--stage-success);
}

.refund-stages li.is-skipped:not(:last-child)::after {
  width: 0;
  border-left: 2px dashed var(--border-medium);
  background: transparent;
}

.refund-stage__marker {
  position: relative;
  z-index: 1;
  width: 30px;
  height: 30px;
  box-sizing: border-box;
  display: grid;
  place-items: center;
  border: 2px solid var(--border-medium);
  border-radius: 50%;
  color: var(--text-tertiary);
  background: var(--bg-card);
  font-size: 12px;
  font-weight: 750;
  font-variant-numeric: tabular-nums;
}

.refund-stage__copy {
  min-width: 0;
  display: grid;
  gap: 3px;
  padding-top: 1px;
}

.refund-stage__copy strong {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
  line-height: 1.45;
}

.refund-stage__copy small {
  min-height: 18px;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}

.refund-stages li.is-done .refund-stage__marker {
  border-color: var(--stage-success);
  color: var(--palette-hex-ffffff);
  background: var(--stage-success);
}

.refund-stages li.is-done .refund-stage__copy strong,
.refund-stages li.is-current .refund-stage__copy strong,
.refund-stages li.is-error .refund-stage__copy strong {
  color: var(--text-primary);
}

.refund-stages li.is-current .refund-stage__marker,
.refund-stages li.is-error .refund-stage__marker {
  border-color: currentColor;
  color: var(--stage-info);
  background: color-mix(in srgb, currentColor 10%, var(--bg-card));
  box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 12%, transparent);
}

.refund-stages li.tone-warning .refund-stage__marker { color: var(--stage-warning); }
.refund-stages li.tone-danger .refund-stage__marker { color: var(--stage-danger); }
.refund-stages li.tone-brand .refund-stage__marker { color: var(--stage-brand); }

.refund-stages li.is-skipped .refund-stage__marker {
  border-style: dashed;
  color: var(--text-tertiary);
  background: var(--bg-secondary);
}

.refund-stage__sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.refund-stages li:last-child {
  padding-bottom: 0;
}

@media (min-width: 768px) {
  .refund-stages {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .refund-stages li {
    grid-template-columns: 1fr;
    justify-items: center;
    gap: 8px;
    padding: 0 8px;
    text-align: center;
  }

  .refund-stages li:not(:last-child)::after,
  .refund-stages li.is-skipped:not(:last-child)::after {
    top: 14px;
    right: calc(-50% + 15px);
    bottom: auto;
    left: calc(50% + 15px);
    width: auto;
    height: 2px;
    border: 0;
    background: var(--border-medium);
  }

  .refund-stages li.is-done:not(:last-child)::after {
    background: var(--stage-success);
  }

  .refund-stages li.is-skipped:not(:last-child)::after {
    height: 0;
    border-top: 2px dashed var(--border-medium);
    background: transparent;
  }

  .refund-stage__copy {
    justify-items: center;
    padding-top: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .refund-stage__marker { transition: none; }
}
</style>
