<template>
  <section class="seller-form-section">
    <header>
      <span v-if="number" aria-hidden="true">{{ number }}</span>
      <div><h2>{{ title }}</h2><p v-if="description">{{ description }}</p></div>
      <slot name="header-action" />
    </header>
    <div class="seller-form-section-body"><slot /></div>
  </section>
</template>

<script setup>
defineProps({
  number: { type: String, default: '' },
  title: { type: String, required: true },
  description: { type: String, default: '' }
})
</script>

<style scoped>
.seller-form-section { border: 1px solid var(--seller-border); border-radius: 14px; background: var(--seller-surface); box-shadow: var(--seller-shadow-sm); }
.seller-form-section > header { display: flex; align-items: flex-start; gap: 12px; padding: 18px 20px; border-bottom: 1px solid var(--seller-border); }
.seller-form-section > header > span { flex: 0 0 30px; width: 30px; height: 30px; display: grid; place-items: center; border-radius: 9px; color: var(--palette-hex-ffffff); background: var(--seller-navy); font: 700 12px/1 ui-monospace, SFMono-Regular, Menlo, monospace; }
.seller-form-section header div { min-width: 0; flex: 1; }
.seller-form-section h2 { margin: 0; color: var(--seller-ink); font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", STSong, serif; font-size: 17px; font-weight: 650; }
.seller-form-section header p { margin: 5px 0 0; color: var(--seller-muted); font-size: 12px; line-height: 1.55; }
.seller-form-section-body { padding: 20px; }
@media (max-width: 640px) { .seller-form-section > header, .seller-form-section-body { padding: 16px; } }
</style>
