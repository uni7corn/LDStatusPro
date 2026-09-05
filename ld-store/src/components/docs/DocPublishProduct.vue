<template>
  <div class="doc-content">
    <h2 id="purpose">发布前先完成两项选择</h2>
    <p class="lead">先确定物品如何交付，再确认卖家收款已可用。普通物品和自动发卡物品都通过平台订单支付，也都依赖卖家自己的 LDC 收款配置。</p>

    <HelpPath :items="[{ label: '卖家后台', to: '/seller' }, { label: '发布物品', to: '/seller/products/new' }]" />

    <h2 id="prepare">准备资料</h2>
    <ul>
      <li>LDC 收款设置显示可用；如果尚未配置，先完成 <router-link to="/docs/payment-settings">LDC 收款接入</router-link>。</li>
      <li>简洁明确的标题、分类、详情说明、LDC 价格和 HTTPS 图片链接。</li>
      <li>普通物品准备可履约数量；自动发卡准备独立卡密库存或一份共享内容。</li>
      <li>说明使用条件、有效期、交付后如何验证，以及合理的售后边界。</li>
    </ul>

    <HelpCallout title="不要把收款密钥或真实卡密写进公开详情" tone="danger">
      Client Key 只保存在收款设置；卡密只填入自动发卡库存区域。详情描述和图片对所有访客可见。
    </HelpCallout>

    <h2 id="normal-product">发布普通物品</h2>
    <p>选择“普通物品”，设置可售库存并写清卖家如何履约。买家在平台内完成 LDC 支付后，订单通常进入待发货，由卖家到订单管理手动填写交付说明。</p>
    <HelpCallout title="首次发布前需要确认履约规则" tone="warning">
      普通物品须在支付后 72 小时内真实交付。系统会在 48 小时下架物品，到期自动发起全额退款；3 笔有效超时记录会限制新增交易 7 天。<router-link to="/docs/shipping-deadline">阅读全文</router-link>
    </HelpCallout>
    <HelpSteps :steps="normalSteps" />

    <h2 id="auto-delivery">发布自动发卡物品</h2>
    <p>选择“自动发卡”，再选择独立卡密或共享卡密。独立卡密逐条发放；共享卡密重复发放同一内容、固定每位用户永久累计限购一件，商城库存显示 9999。</p>
    <HelpSteps :steps="cdkSteps" />
    <p>不确定模式时，先查看 <router-link to="/docs/product-types">选择物品与卡密类型</router-link>。后续虽然可以切换，但会涉及库存暂停、恢复或迁移，并重新审核。</p>

    <h2 id="purchase-limit">设置购买限制</h2>
    <p>普通物品和独立卡密可以选择不限制、每笔订单最多 X 件，或每位用户累计最多 X 件。选择按用户累计后，还可以设置永久累计或最近 N 天的滚动周期；共享卡密由系统固定为每位用户永久累计一件。</p>
    <ul>
      <li>“每笔订单最多”只限制当前订单，买家之后仍可再次下单。</li>
      <li>“永久累计”统计该物品生命周期内的全部成交；适合一人只能领取固定总量的场景。</li>
      <li>“滚动周期”统计最近 N × 24 小时，例如“最近 7 天每位用户 1 件”；不是按自然周或每天零点重置。</li>
      <li>待支付订单会暂时占用额度，取消或过期后释放；已支付和已退款订单在永久模式下始终计入，在滚动模式下超出周期后自然释放。</li>
      <li>只修改购买限制不会触发重新审核；切换独立与共享卡密仍会重新审核。</li>
    </ul>
    <HelpCallout title="数量设为 1，即可实现“7 天内只能买一单”" tone="info">
      选择“每位用户累计最多 → 滚动周期”，填写 1 件和 7 天。限制按账号、站点和当前物品统计，多账号不属于本功能的防护范围。
    </HelpCallout>

    <h2 id="submit-review">提交与审核结果</h2>
    <dl class="status-list">
      <div><dt>审核中</dt><dd>资料已提交，等待自动审核或人工复核。不要重复创建相同物品。</dd></div>
      <div><dt>审核通过</dt><dd>物品按页面当前状态进入可展示或可销售流程。</dd></div>
      <div><dt>审核不通过</dt><dd>根据页面原因修改资料后重新提交，避免只改无关字段。</dd></div>
      <div><dt>人工复核</dt><dd>自动检查无法确认时转由人工处理；不承诺固定完成时间。</dd></div>
    </dl>

    <h2 id="test-and-result">发布后检查</h2>
    <ol>
      <li>到“我的物品”查看用户可见的中文审核状态。</li>
      <li>审核通过后打开物品详情，复核标题、图片、价格、库存、限购和交付说明。</li>
      <li>自动发卡检查模式和可用库存；普通物品确认卖家订单提醒可见。</li>
      <li>如页面提供测试模式，只按页面提示验证，不把测试物品当正式成交。</li>
    </ol>

    <h2 id="troubleshooting">常见异常</h2>
    <ul>
      <li>无法提交：逐项检查必填字段、图片 URL、价格、库存和收款状态。</li>
      <li>卡密数量不符：确认当前是独立还是共享模式；共享模式商城固定显示 9999。</li>
      <li>审核不通过：按当前页面原因修改，不依赖旧文档里的固定审核时长或限额。</li>
      <li>支付后未自动交付：检查收款通知测试和卡密库存，再到订单页处理异常。</li>
    </ul>

    <div class="help-actions">
      <router-link to="/seller/products/new">发布物品</router-link>
      <router-link to="/seller/products" class="secondary">管理我的物品</router-link>
    </div>
  </div>
</template>

<script setup>
import HelpCallout from './HelpCallout.vue'
import HelpPath from './HelpPath.vue'
import HelpSteps from './HelpSteps.vue'

const normalSteps = [
  { title: '选择普通物品', description: '确认该物品需要你在成交后人工确认或交付。' },
  { title: '填写展示与交易信息', description: '完成标题、分类、说明、图片、价格和普通库存。' },
  { title: '说明履约方式', description: '告诉买家支付后在哪里等待、需要提供什么以及预计如何交付。' },
  { title: '提交审核', description: '确认公开内容不含密钥、隐私或违规信息。', result: '审核通过后留意卖家后台的待发货提醒。' }
]
const cdkSteps = [
  { title: '选择自动发卡', description: '仅用于支付完成后可以直接交付的数字内容。' },
  { title: '选择卡密模式', description: '每单不同选独立卡密；每单相同选共享卡密。' },
  { title: '录入交付内容', description: '独立模式录入多条库存；共享模式只维护一份共享内容。' },
  { title: '提交并复核', description: '审核通过后，从物品详情和库存管理确认模式正确。', result: '系统会按支付结果自动交付，卖家仍需关注异常订单。' }
]
</script>
