<template><div class="refund-request-boundary" :data-available="available" :data-open="open" :aria-busy="submitting"><slot /></div></template>
<script setup lang="ts">defineProps<{ available: boolean; open: boolean; submitting: boolean }>()</script>
<style scoped>.refund-request-boundary { display: contents; }</style>
