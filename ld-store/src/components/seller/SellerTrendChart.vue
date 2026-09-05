<template>
  <div class="seller-chart-wrap">
    <div
      v-show="!chartFailed && hasData"
      ref="chartElement"
      class="seller-chart"
      role="img"
      :aria-label="chartAriaLabel"
    ></div>
    <div v-if="!hasData" class="seller-chart-empty">
      <BarChart3 :size="24" aria-hidden="true" />
      <strong>本期暂无可绘制数据</strong>
      <span>保留真实零值，不显示误导性的趋势坐标。</span>
    </div>
    <div v-else-if="chartFailed" class="seller-chart-empty" role="alert">
      <AlertCircle :size="24" aria-hidden="true" />
      <strong>趋势图加载失败</strong>
      <span>下方数据表仍可正常查看。</span>
      <button type="button" @click="renderChart">重新加载</button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { AlertCircle, BarChart3 } from '@lucide/vue'

echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, AriaComponent, SVGRenderer])

const props = defineProps({
  trend: { type: Array, default: () => [] },
  view: { type: String, default: 'revenue' }
})

const chartElement = ref(null)
const chartFailed = ref(false)
let chart = null
let resizeObserver = null
let themeObserver = null

const chartCopy = computed(() => ({
  revenue: { title: '收入趋势', unit: 'LDC', names: ['商品销售', '求购服务'] },
  orders: { title: '订单趋势', unit: '笔', names: ['商品订单', '求购服务'] },
  views: { title: '物品浏览趋势', unit: '次', names: ['物品浏览'] }
})[props.view] || { title: '经营趋势', unit: '', names: [] })

const hasData = computed(() => props.trend.some(item => {
  if (props.view === 'revenue') return Number(item.productRevenue) || Number(item.serviceRevenue)
  if (props.view === 'orders') return Number(item.productOrders) || Number(item.serviceOrders)
  return Number(item.productViews)
}))

const chartAriaLabel = computed(() => `${chartCopy.value.title}，共 ${props.trend.length} 个日期，可在下方展开数据表查看精确值。`)

function getPalette() {
  const shell = chartElement.value?.closest('.seller-shell')
  const styles = shell ? getComputedStyle(shell) : getComputedStyle(document.documentElement)
  const fallbackText = styles.color || 'currentColor'
  const readColor = (domainToken, semanticToken, fallback = fallbackText) => (
    styles.getPropertyValue(domainToken).trim()
    || styles.getPropertyValue(semanticToken).trim()
    || fallback
  )
  return {
    text: readColor('--seller-muted', '--text-paper-secondary'),
    line: readColor('--seller-jade', '--action-paper-accent'),
    border: readColor('--seller-border', '--border-paper-default'),
    surface: readColor('--seller-surface', '--surface-paper-card', 'transparent'),
    navy: readColor('--seller-navy', '--action-paper-primary')
  }
}

function createSeries() {
  if (props.view === 'revenue') {
    return [
      { name: '商品销售', type: 'line', smooth: 0.24, showSymbol: false, data: props.trend.map(item => item.productRevenue), lineStyle: { width: 2.5 } },
      { name: '求购服务', type: 'line', smooth: 0.24, showSymbol: false, data: props.trend.map(item => item.serviceRevenue), lineStyle: { width: 2, type: 'dashed' } }
    ]
  }
  if (props.view === 'orders') {
    return [
      { name: '商品订单', type: 'bar', stack: 'orders', barMaxWidth: 18, data: props.trend.map(item => item.productOrders) },
      { name: '求购服务', type: 'bar', stack: 'orders', barMaxWidth: 18, data: props.trend.map(item => item.serviceOrders), itemStyle: { decal: { symbol: 'rect', dashArrayX: [2, 3], dashArrayY: [3, 2] } } }
    ]
  }
  return [{ name: '物品浏览', type: 'line', smooth: 0.24, showSymbol: false, areaStyle: { opacity: 0.08 }, data: props.trend.map(item => item.productViews), lineStyle: { width: 2.5 } }]
}

async function renderChart() {
  if (!hasData.value || !chartElement.value) return
  chartFailed.value = false
  try {
    await nextTick()
    const palette = getPalette()
    if (!chart) chart = echarts.init(chartElement.value, null, { renderer: 'svg' })
    chart.setOption({
      animationDuration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 220,
      color: [palette.line, palette.navy],
      aria: { enabled: true, decal: { show: true } },
      tooltip: {
        trigger: 'axis',
        confine: true,
        appendToBody: false,
        backgroundColor: palette.surface,
        borderColor: palette.border,
        textStyle: { color: palette.text }
      },
      legend: { top: 0, right: 0, icon: 'roundRect', textStyle: { color: palette.text } },
      grid: { left: 16, right: 12, top: 42, bottom: 8, containLabel: true },
      xAxis: {
        type: 'category',
        boundaryGap: props.view === 'orders',
        data: props.trend.map(item => item.date.slice(5)),
        axisLine: { lineStyle: { color: palette.border } },
        axisTick: { show: false },
        axisLabel: { color: palette.text, hideOverlap: true, interval: Math.max(Math.ceil(props.trend.length / 7) - 1, 0) }
      },
      yAxis: {
        type: 'value',
        minInterval: props.view === 'revenue' ? 0 : 1,
        name: chartCopy.value.unit,
        nameTextStyle: { color: palette.text, align: 'right' },
        splitLine: { lineStyle: { color: palette.border, type: 'dashed', opacity: 0.65 } },
        axisLabel: { color: palette.text }
      },
      series: createSeries()
    }, true)
  } catch {
    chartFailed.value = true
  }
}

watch(() => [props.trend, props.view], renderChart, { deep: true })

onMounted(() => {
  renderChart()
  resizeObserver = new ResizeObserver(() => chart?.resize())
  if (chartElement.value) resizeObserver.observe(chartElement.value)
  themeObserver = new MutationObserver(renderChart)
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  themeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.seller-chart-wrap { min-height: 300px; }
.seller-chart { width: 100%; height: 300px; overflow: hidden; }
.seller-chart-empty { min-height: 280px; display: grid; place-items: center; align-content: center; gap: 8px; color: var(--seller-muted); text-align: center; }
.seller-chart-empty strong { color: var(--seller-ink); font-size: 15px; }
.seller-chart-empty span { max-width: 360px; font-size: 13px; }
.seller-chart-empty button { min-height: 40px; margin-top: 4px; padding: 0 14px; border: 1px solid var(--seller-border); border-radius: 9px; color: var(--seller-ink); background: var(--seller-surface); }
@media (max-width: 640px) {
  .seller-chart-wrap, .seller-chart { min-height: 248px; height: 248px; }
}
</style>
