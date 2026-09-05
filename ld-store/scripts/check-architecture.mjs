import { readdirSync, readFileSync, statSync } from 'node:fs'
import { relative, resolve, sep } from 'node:path'

const root = resolve(import.meta.dirname, '..')
const sourceRoot = resolve(root, 'src')
const extensions = new Set(['.js', '.ts', '.vue'])
const apiAllowlist = new Set([
  'src/views/Login.vue',
  'src/views/AuthCallback.vue',
  'src/views/LdImage.vue'
])

function sourceFiles(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name)
    if (statSync(path).isDirectory()) return sourceFiles(path)
    const extension = name.slice(name.lastIndexOf('.'))
    return extensions.has(extension) ? [path] : []
  })
}

function displayPath(path) {
  return relative(root, path).split(sep).join('/')
}

const failures = []
for (const file of sourceFiles(sourceRoot)) {
  const path = displayPath(file)
  const source = readFileSync(file, 'utf8')

  const isService = path.startsWith('src/services/')
  if (isService && /(?:@\/|\.\.\/)+(?:views|components|stores)\//.test(source)) {
    failures.push(`${path}: service 不能反向依赖 view、component 或 store`)
  }

  if (/(?:@\/stores\/shop|(?:\.\.\/)+stores\/shop|\.\/shop)(?:['"]|\b)/.test(source)) {
    failures.push(`${path}: 禁止重新引入已删除的全能 shop store`)
  }

  const isUiOrStore = /^(?:src\/(?:views|components|stores)\/)/.test(path)
  if (isUiOrStore && !apiAllowlist.has(path)) {
    if (/from\s+['"][^'"]*utils\/api['"]/.test(source)) {
      failures.push(`${path}: API Client 只能由 service 导入`)
    }
    if (/\bfetch\s*\(/.test(source)) {
      failures.push(`${path}: 页面、组件和 store 不能直接发起 fetch`)
    }
  }

  if (path === 'src/views/Orders.vue') {
    for (const boundary of ['useOrderListController', 'useOrderActions', 'BuyerOrderList', 'SellerOrderTable', 'ManualDeliveryEditor']) {
      if (!source.includes(boundary)) failures.push(`${path}: 订单 Shell 必须通过 ${boundary} 边界组织`)
    }
  }

  if (path === 'src/views/OrderDetail.vue' && !source.includes('useOrderDetail')) {
    failures.push(`${path}: 订单详情加载与刷新必须由 useOrderDetail 管理`)
  }

  if (path === 'src/components/order/OrderRefundPanel.vue') {
    if (!source.includes('useOrderRefund')) failures.push(`${path}: 退款状态机必须由 useOrderRefund 管理`)
    if (/from\s+['"][^'"]*services\//.test(source)) failures.push(`${path}: 退款视图不能直接依赖 service`)
  }
}

if (failures.length) {
  console.error('Architecture boundary violations:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('Architecture boundary validation passed')
