<template>
  <div class="doc-content">
    <h2 id="purpose">把待处理订单从全部记录中找出来</h2>
    <p class="lead">卖家订单页同时服务商品销售和求购服务，但两类记录通过来源切换分流。处理前先确认当前订单类型。</p>

    <HelpPath :items="[{ label: '卖家后台', to: '/seller' }, { label: '订单管理', to: '/seller/orders' }]" />

    <h2 id="prepare">处理前准备</h2>
    <ul>
      <li>确认当前查看“商品销售”还是“求购服务”。</li>
      <li>用订单号、买家或物品关键词搜索，并结合页面状态筛选。</li>
      <li>普通物品准备交付说明；异常自动发卡准备核对库存和收款通知。</li>
      <li>不要在交付备注中写入与本订单无关的账号密钥或他人隐私。</li>
    </ul>

    <h2 id="order-sources">商品销售与求购服务</h2>
    <HelpTable :columns="sourceColumns" :rows="sourceRows" />

    <h2 id="pending-delivery">处理待发货订单</h2>
    <HelpSteps :steps="deliverySteps" />
    <HelpCallout title="先看发货截止时间" tone="warning">
      普通物品按支付成功后连续 72 小时计算。48 小时未发货会下架物品；到期后发货入口停止，系统自动发起全额退款。无法履约时请在截止前使用主动全额退款。<router-link to="/docs/shipping-deadline">查看计次和异常规则</router-link>
    </HelpCallout>
    <HelpCallout title="先确认支付结果，再交付" tone="warning">
      只有订单页面确认已支付并进入需要履约的状态时才开始发货。不要依据买家单独发送的截图跳过订单状态。
    </HelpCallout>

    <h2 id="auto-delivery-orders">自动发卡订单也需要关注</h2>
    <p>正常情况下，独立卡密或共享卡密会在支付通知确认后自动写入订单。若订单仍显示待发货或没有交付内容：</p>
    <ol>
      <li>核对卖家收款设置和通知测试是否通过。</li>
      <li>独立卡密检查是否有可用库存；共享卡密检查共享内容是否有效。</li>
      <li>进入订单详情查看系统提示，按页面提供的操作补充处理。</li>
      <li>记录异常订单号，避免重复对同一订单交付多份内容。</li>
    </ol>

    <h2 id="status-and-result">完成后确认</h2>
    <dl class="status-list">
      <div><dt>待发货</dt><dd>订单已等待卖家处理，是经营概览和订单页优先关注的待办。</dd></div>
      <div><dt>超时退款处理中</dt><dd>订单已过发货期限，不可继续发货；关注退款成功、失败或待核对结果。</dd></div>
      <div><dt>已发货</dt><dd>交付信息已经写入订单，买家可在订单详情查看。</dd></div>
      <div><dt>已完成</dt><dd>交易流程结束；仍需按已承诺范围处理必要售后。</dd></div>
      <div><dt>已取消 / 已过期</dt><dd>不要继续交付；如状态与实际支付不符，先反馈核对。</dd></div>
    </dl>

    <h2 id="refund-after-sales">处理退款售后</h2>
    <p>买家提交退款后，卖家后台的“退款售后”会出现新待办。进入原订单后可联系买家并标记协商、填写理由拒绝，或确认全额退款。请于订单显示的处理截止时间前同意退款或说明理由拒绝，协商和发货不延长申请时限。系统会在截止前 3 小时提醒，逾期未决定自动同意并发起退款。退款完成后不再对该订单发货。</p>
    <HelpCallout title="退款同意后不可撤销" tone="danger">
      点击“同意并退款”会立即尝试从原收款应用全额退回 LDC。先核对订单、买家和协商结果，再进行最终确认。
    </HelpCallout>

    <h2 id="troubleshooting">找不到或无法处理订单</h2>
    <ul>
      <li>检查商品销售 / 求购服务来源开关是否选错。</li>
      <li>清除过窄的状态、时间或关键词筛选后重新搜索。</li>
      <li>确认你登录的是该物品卖家或求购服务方账号。</li>
      <li>按钮不可用时阅读订单当前状态提示，不要通过编辑物品绕过订单流程。</li>
    </ul>

    <div class="help-actions">
      <router-link to="/seller/orders">打开订单管理</router-link>
      <router-link to="/seller/refunds" class="secondary">打开退款售后</router-link>
      <router-link to="/docs/payment-settings" class="secondary">检查收款配置</router-link>
    </div>
  </div>
</template>

<script setup>
import HelpCallout from './HelpCallout.vue'
import HelpPath from './HelpPath.vue'
import HelpSteps from './HelpSteps.vue'
import HelpTable from './HelpTable.vue'

const sourceColumns = [
  { key: 'source', label: '订单来源' },
  { key: 'contains', label: '包含内容' },
  { key: 'mainTask', label: '主要任务' }
]
const sourceRows = [
  { source: '商品销售', contains: '普通物品、独立卡密、共享卡密订单', mainTask: '发货、检查自动交付和售后' },
  { source: '求购服务', contains: '你承接的求购订单', mainTask: '按洽谈结果履约并保留沟通记录' }
]
const deliverySteps = [
  { title: '筛选待发货', description: '选择正确订单来源和“待发货”状态，优先处理最早订单。' },
  { title: '打开订单详情', description: '核对订单号、买家、物品、数量、支付状态和约定。' },
  { title: '完成实际交付', description: '普通物品按说明履约；自动发卡异常先排查库存和通知。' },
  { title: '填写并确认发货', description: '只写买家需要的交付信息，提交后再次检查订单状态。', result: '经营概览中的待发货数量会随已处理订单更新。' }
]
</script>
