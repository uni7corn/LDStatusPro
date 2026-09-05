<template><div class="refund-negotiation-boundary" :data-status="status" :aria-busy="submitting"><slot /></div></template>
<script setup lang="ts">defineProps<{ status: string; submitting: boolean }>()</script>
<style scoped>.refund-negotiation-boundary { display: contents; }</style>
