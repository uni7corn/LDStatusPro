<template>
  <section class="product-picker" aria-labelledby="promotion-product-title">
    <header class="section-heading">
      <div><span class="step-label">第一步</span><h2 id="promotion-product-title">选择推广物品</h2></div>
      <span class="item-count">{{ products.length }} 件可查看</span>
    </header>

    <div v-if="selected && !expanded" class="selected-product">
      <div class="selected-cover">
        <img v-if="hasImage(selected)" :src="imageSource(selected)" alt="" @error="markBroken(selected)" />
        <span v-else class="empty-cover">{{ imageMessage(selected) }}</span>
      </div>
      <div class="selected-copy">
        <span class="category-label"><span>所属分类</span><strong>{{ selected.categoryName || '未分类' }}</strong></span>
        <h3>{{ selected.name }}</h3>
        <span class="product-state" :class="{ ongoing: selected.currentTopOrder }">{{ productState(selected) }}</span>
      </div>
      <button ref="changeButton" type="button" class="change-product" :disabled="disabled" @click="openPicker">更换物品<ArrowLeftRight :size="15" aria-hidden="true" /></button>
    </div>

    <div v-else>
      <label class="search-box" for="promotion-product-search"><Search :size="18" aria-hidden="true" /><span class="sr-only">搜索物品名称</span><input id="promotion-product-search" ref="searchInput" v-model="search" type="search" placeholder="搜索物品名称" :disabled="disabled" /></label>
      <fieldset class="product-gallery" :disabled="disabled">
        <legend class="sr-only">要推广的物品</legend>
        <label v-for="product in filtered" :key="product.id" class="product-choice" :class="{ selected: String(modelValue) === String(product.id) }">
          <span class="choice-cover">
            <img v-if="hasImage(product)" :src="imageSource(product)" alt="" loading="lazy" @error="markBroken(product)" />
            <span v-else class="empty-cover">{{ imageMessage(product) }}</span>
            <input type="radio" name="promotion-product" :value="String(product.id)" :checked="String(modelValue) === String(product.id)" @change="choose(product.id)" />
            <span class="choice-marker" aria-hidden="true"><Check v-if="String(modelValue) === String(product.id)" :size="14" /></span>
          </span>
          <span class="choice-copy">
            <span class="category-tag">{{ product.categoryName || '未分类' }}</span>
            <strong class="product-name">{{ product.name }}</strong>
            <span class="product-state" :class="{ ongoing: product.currentTopOrder }">{{ productState(product) }}</span>
          </span>
        </label>
      </fieldset>
      <p v-if="!filtered.length" class="empty-copy">没有找到匹配的物品，试试其他名称。</p>
      <button v-if="selected" type="button" class="keep-selection" @click="keepSelection">保留当前物品</button>
    </div>
    <p class="field-note">仅展示已上架物品；已有服务的物品也可查看和处理。</p>
    <button v-if="hasImageErrors" class="retry-images" type="button" :disabled="disabled" @click="retryImages">重试图片</button>
  </section>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { ArrowLeftRight, Check, Search } from '@lucide/vue'
import { getTopServiceOrderPresentation } from '@/utils/topServiceOrder'
const props = defineProps({ products: { type: Array, default: () => [] }, modelValue: { type: [String, Number], default: '' }, disabled: Boolean })
const emit = defineEmits(['change', 'retry-images'])
const search = ref('')
const expanded = ref(false)
const searchInput = ref(null)
const changeButton = ref(null)
const brokenImages = ref({})
const selected = computed(() => props.products.find(p => String(p.id) === String(props.modelValue)))
const filtered = computed(() => props.products.filter(p => p.name.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase())))
const hasImageErrors = computed(() => props.products.some(p => p.imageError || brokenImages.value[imageSource(p)]))
function imageSource(product) { return String(product.imageUrl || product.image_url || '').trim() }
function hasImage(product) { return imageSource(product) && !brokenImages.value[imageSource(product)] }
function imageMessage(product) { return product.imageLoading ? '图片加载中…' : product.imageError || brokenImages.value[imageSource(product)] ? '图片加载失败' : '暂无图片' }
function markBroken(product) { brokenImages.value[imageSource(product)] = true }
function retryImages() { brokenImages.value = {}; emit('retry-images') }
function productState(product) { return product.currentTopOrder ? getTopServiceOrderPresentation(product.currentTopOrder).label : '可开通推广' }
async function keepSelection() { expanded.value = false; await nextTick(); changeButton.value?.focus({ preventScroll: true }) }
async function choose(id) { emit('change', id); await keepSelection() }
async function openPicker() { expanded.value = true; await nextTick(); searchInput.value?.focus() }
</script>

<style scoped>
.section-heading { display:flex; justify-content:space-between; align-items:center; gap:16px; margin-bottom:22px; }
.step-label,.item-count { color:var(--seller-muted); font-size:12px; }
h2 { margin:5px 0 0; font-size:19px; color:var(--seller-ink); font-weight:650; }
.item-count { white-space:nowrap; }
.selected-product { display:grid; grid-template-columns:120px minmax(0,1fr); gap:20px; align-items:start; position:relative; }
.selected-cover { grid-row:1/3; aspect-ratio:1; border-radius:16px; overflow:hidden; background:var(--seller-surface-soft); }
.selected-cover img,.choice-cover img { width:100%; height:100%; object-fit:cover; display:block; }
.empty-cover { display:grid; place-items:center; width:100%; height:100%; background:var(--seller-surface-soft); color:var(--seller-muted); font-size:12px; letter-spacing:.08em; }
.selected-copy { min-width:0; }
.category-label { display:inline-flex; flex-wrap:wrap; align-items:center; gap:8px; font-size:12px; }
.category-label>span { color:var(--seller-muted); }
.category-label strong,.category-tag { padding:4px 10px; border-radius:6px; background:var(--service-gold-soft); color:var(--service-gold-ink); font-size:12px; line-height:1.5; font-weight:650; }
.selected-copy h3 { color:var(--seller-ink); font-size:18px; line-height:1.6; font-weight:600; margin:9px 0 8px; overflow-wrap:anywhere; }
.product-state { display:flex; align-items:center; gap:6px; color:var(--seller-muted); font-size:12px; line-height:1.6; }
.product-state::before { content:''; width:5px; height:5px; border-radius:50%; flex:0 0 auto; background:var(--seller-jade); }
.product-state.ongoing { color:var(--service-gold-ink); }
.product-state.ongoing::before { background:var(--service-gold); }
button { display:inline-flex; align-items:center; justify-content:center; gap:8px; min-height:44px; padding:8px 12px; border:1px solid var(--seller-border); border-radius:9px; color:var(--seller-ink); background:var(--seller-surface-strong); font-size:13px; }
.change-product { grid-column:2; justify-self:start; margin-top:-10px; }
button:disabled,fieldset:disabled { opacity:.6; }
.search-box { display:flex; align-items:center; gap:10px; padding:0 14px; border:1px solid var(--seller-border); border-radius:10px; background:var(--seller-surface-strong); color:var(--seller-muted); }
.search-box input { min-width:0; width:100%; min-height:46px; border:0; background:transparent; color:var(--seller-ink); font:inherit; font-size:14px; }
.search-box:focus-within { outline:2px solid var(--seller-jade); outline-offset:2px; }
.search-box input:focus-visible { outline:0; }
.product-gallery { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:20px 14px; min-width:0; padding:4px; margin:18px -4px 0; max-height:440px; overflow:auto; border:0; scroll-padding:8px; }
.product-choice { min-width:0; cursor:pointer; border-radius:14px; }
.choice-cover { display:block; position:relative; aspect-ratio:4/3; border-radius:12px; overflow:hidden; background:var(--seller-surface-soft); border:1px solid var(--seller-border); }
.choice-cover input { position:absolute; z-index:1; top:0; right:0; width:44px; height:44px; margin:0; opacity:0; cursor:pointer; }
.choice-marker { position:absolute; top:11px; right:11px; display:grid; place-items:center; width:23px; height:23px; border:1px solid var(--palette-hex-68737c); border-radius:50%; background:var(--palette-hex-fffefa); color:var(--palette-hex-ffffff); pointer-events:none; }
.selected .choice-marker { border-color:var(--seller-jade-strong); background:var(--seller-jade-strong); color:var(--seller-surface-strong); }
.product-choice.selected .choice-cover { outline:2px solid var(--seller-jade-strong); outline-offset:2px; }
.product-choice:has(input:focus-visible) { outline:3px solid var(--seller-jade); outline-offset:3px; }
.product-choice input:focus-visible { outline:0; }
.choice-copy { display:grid; justify-items:start; gap:8px; padding:12px 2px 2px; }
.product-name { color:var(--seller-ink); font-size:14px; line-height:1.65; font-weight:600; overflow-wrap:anywhere; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.field-note,.empty-copy { margin:18px 0 0; color:var(--seller-muted); font-size:12px; line-height:1.8; }
.keep-selection { margin-top:16px; }
.retry-images { margin-top:10px; color:var(--service-rose-ink); }
@media(hover:hover) { .product-choice:hover .choice-cover { border-color:var(--seller-jade); } button:hover { border-color:var(--seller-border-strong); background:var(--seller-surface-soft); } }
@media(max-width:640px) { .selected-product { grid-template-columns:94px minmax(0,1fr); gap:16px; } .selected-copy h3 { font-size:16px; } .selected-cover { border-radius:13px; } .product-gallery { grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px 12px; max-height:470px; } .category-label { gap:5px; } .category-label>span { font-size:11px; } .item-count { font-size:11px; } }
@media(prefers-reduced-motion:no-preference) { .choice-cover,button { transition:border-color .16s ease,background-color .16s ease; } }
</style>
