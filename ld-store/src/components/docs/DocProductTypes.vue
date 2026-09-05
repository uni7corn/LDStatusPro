<template>
  <div class="doc-content">
    <h2 id="purpose">先按交付方式选择</h2>
    <p class="lead">普通物品适合需要人工履约的内容；自动发卡适合支付后立即交付的卡密。自动发卡再分为独立卡密和共享卡密。</p>

    <HelpTable :columns="typeColumns" :rows="typeRows" caption="三种交付方式对比" />

    <HelpCallout title="三种类型都在平台内支付" tone="info">
      普通物品不是站外交易入口。普通物品与自动发卡物品都需要卖家配置 LDC 收款，并在 LD 士多订单中完成支付。
    </HelpCallout>

    <h2 id="normal-product">普通物品</h2>
    <HelpPath :items="[{ label: '卖家后台', to: '/seller' }, { label: '发布物品', to: '/seller/products/new' }, { label: '普通物品' }]" />
    <p>适合代办服务、人工交付的数字内容或其他需要卖家确认的物品。买家支付后，订单通常进入待发货，卖家在订单页填写交付说明并完成履约。</p>
    <HelpCallout title="选择普通物品即接受 72 小时履约规则" tone="warning">
      支付 48 小时后仍未发货，物品会被下架；72 小时后系统自动发起实付全额退款。积压订单解决前不能重新上架。<router-link to="/docs/shipping-deadline">查看发货时限与处罚规则</router-link>
    </HelpCallout>

    <h2 id="independent-cdk">独立卡密：逐条消耗库存</h2>
    <ul>
      <li>每条卡密是一份独立库存，成交后按库存逐条发放。</li>
      <li>适合激活码、兑换码、一人一号等不能重复使用的内容。</li>
      <li>可在物品管理中追加、查看和管理可用卡密；库存不足时物品可能售罄。</li>
      <li>销量按实际成交累计，库存按剩余可发放卡密数量变化。</li>
    </ul>

    <h2 id="shared-cdk">共享卡密：重复发放同一内容</h2>
    <ul>
      <li>每笔成交都发放同一份共享内容，不逐条扣减卡密。</li>
      <li>每位用户在该物品生命周期内永久累计限购一件，已购买后不能通过拆单再次获得。</li>
      <li>商城库存统一显示 <strong>9999</strong>，表示共享模式的展示库存，并非真实生成了 9999 条卡密。</li>
      <li>销量仍按实际成功成交数量累计，不会因为共享模式被固定或重置。</li>
    </ul>

    <HelpCallout title="共享卡密适合可重复使用的固定内容" tone="warning">
      如果内容包含一次性凭证、个人账号或每位买家必须不同的授权码，请使用独立卡密。
    </HelpCallout>

    <h2 id="choose-mode">快速决策</h2>
    <div class="decision-grid">
      <div class="decision-card"><span class="card-kicker">需要人工确认</span><h3>选择普通物品</h3><p>支付后由卖家联系或手动填写交付信息。</p></div>
      <div class="decision-card"><span class="card-kicker">每单内容不同</span><h3>选择独立卡密</h3><p>预先准备多条卡密，系统逐条发放。</p></div>
      <div class="decision-card"><span class="card-kicker">每单内容相同</span><h3>选择共享卡密</h3><p>只维护一份共享内容，系统重复发放。</p></div>
    </div>

    <h2 id="mode-changes">模式改变后会怎样</h2>
    <p>独立卡密与共享卡密之间可以切换，但会涉及库存暂停、恢复或迁移，并重新进入审核流程。切到共享时，原购买限制会被临时覆盖为每位用户永久累计一件；切回独立时恢复原来的每单、永久累计或滚动周期配置。操作前先阅读 <router-link to="/docs/inventory-management#switch-cdk-mode">切换卡密模式</router-link>，避免误解库存变化。</p>

    <div class="help-actions">
      <router-link to="/seller/products/new">发布物品</router-link>
      <router-link to="/docs/inventory-management" class="secondary">管理卡密库存</router-link>
    </div>
  </div>
</template>

<script setup>
import HelpCallout from './HelpCallout.vue'
import HelpPath from './HelpPath.vue'
import HelpTable from './HelpTable.vue'

const typeColumns = [
  { key: 'type', label: '类型' },
  { key: 'delivery', label: '交付方式' },
  { key: 'stock', label: '库存表现' },
  { key: 'bestFor', label: '适合场景' }
]
const typeRows = [
  { type: '普通物品', delivery: '卖家手动履约', stock: '按卖家设置的普通库存', bestFor: '服务、人工交付内容' },
  { type: '独立卡密', delivery: '支付后逐条自动发放', stock: '按可用卡密数量减少', bestFor: '一次性兑换码、独立账号' },
  { type: '共享卡密', delivery: '支付后重复发放同一内容', stock: '商城固定显示 9999', bestFor: '可重复使用的固定说明或入口' }
]
</script>
