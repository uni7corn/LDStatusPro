<template><section class="product-comments-boundary" :aria-busy="loading" :data-active="active"><slot /></section></template>
<script setup lang="ts">defineProps<{ active: boolean; loading: boolean }>()</script>
<style scoped>.product-comments-boundary { display: contents; }</style>
