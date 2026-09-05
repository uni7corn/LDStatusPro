<script setup>
import { computed } from 'vue'
import { renderAnnouncementContent } from '@/utils/renderAnnouncementContent'
const props = defineProps({ content: { type: String, default: '' }, contentType: { type: String, default: 'text' } })
const html = computed(() => renderAnnouncementContent(props.content, props.contentType))
</script>
<template><div class="announcement-content" v-html="html" /></template>
<style scoped>
.announcement-content{line-height:1.8;color:var(--text-primary-semantic);overflow-wrap:anywhere}.announcement-content :deep(p),.announcement-content :deep(ul),.announcement-content :deep(ol),.announcement-content :deep(blockquote),.announcement-content :deep(pre){margin:0 0 var(--space-4)}.announcement-content :deep(h1),.announcement-content :deep(h2),.announcement-content :deep(h3){margin:var(--space-6) 0 var(--space-3);line-height:1.4;font-weight:600;color:var(--text-primary-semantic)}.announcement-content :deep(h1){font-size:24px}.announcement-content :deep(h2){font-size:20px}.announcement-content :deep(h3){font-size:18px}.announcement-content :deep(ul),.announcement-content :deep(ol){padding-left:var(--space-6);list-style:revert}.announcement-content :deep(img){max-width:100%;height:auto;border-radius:var(--radius-sm)}.announcement-content :deep(pre){padding:var(--space-4);background:var(--surface-subtle);overflow:auto;border-radius:var(--radius-sm)}.announcement-content :deep(table){display:block;max-width:100%;overflow-x:auto;border-collapse:collapse;margin-bottom:var(--space-4)}.announcement-content :deep(td),.announcement-content :deep(th){padding:var(--space-2);border:1px solid var(--border-default-semantic)}.announcement-content :deep(a){color:var(--text-link);text-decoration:underline;text-underline-offset:3px}.announcement-content :deep(blockquote){border-left:3px solid var(--border-strong-semantic);padding-left:var(--space-4);color:var(--text-secondary-semantic)}
</style>
