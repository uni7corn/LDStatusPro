<template>
  <div class="doc-content">
    <h2 id="purpose">退款有期限，处理有记录</h2>
    <p class="lead">LD 士多的退款适用于已支付的商品订单。买家可在支付后 7 天内从订单详情直接申请全额退款，也可先通过 LINUX DO 私信协商；联系卖家不是申请的前置条件。</p>

    <HelpCallout title="只支持原订单全额退款" tone="warning">
      Credit 退款接口要求退回原订单全额，LD 士多不支持部分退款。同一订单只能建立一条退款申请。
    </HelpCallout>
    <HelpCallout title="普通物品超时无需买家申请" tone="info">
      普通物品支付后 72 小时仍未发货，系统会自动发起实付全额退款；已有申请、协商或拒绝不会阻止超时保障。只有 Credit 明确成功后才显示“已退款”。<router-link to="/docs/shipping-deadline">查看发货时限规则</router-link>
    </HelpCallout>

    <HelpCallout title="退款申请 72 小时处理保障" tone="info">
      适用规则的申请会显示准确截止时间（北京时间）。卖家须在申请成功后 72 小时内同意退款或说明理由拒绝；联系协商、发货和确认收货均不延长申请时限。系统在截止前 3 小时提醒卖家，逾期未作决定会自动同意并发起全额退款，Credit 确认成功后通知双方。
    </HelpCallout>
    <p>规则启用前尚未决定的历史申请，通知双方后给予完整 72 小时；原有更早的未发货保障继续有效。具体以订单页显示的期限为准，自动同意不代表即时到账。</p>

    <h2 id="before-request">申请前先准备</h2>
    <ul>
      <li>确认订单已支付，且当前是已支付、已发货或已完成状态；待支付、已取消或已过期订单不能申请。</li>
      <li>可选择先私信卖家，说明订单号和问题；也可直接提交退款申请。</li>
      <li>保留订单页状态、交付结果、沟通时间线和必要截图，但不要公开卡密、密码或 Client Key。</li>
      <li>退款成功后，该订单已使用的优惠券不会恢复；永久累计限购额度不会恢复，滚动限购则仍计入到该笔支付自然移出时间窗口为止。</li>
    </ul>

    <h2 id="buyer-request">买家如何申请退款</h2>
    <HelpPath :items="[{ label: '个人中心', to: '/user' }, { label: '我的订单', to: '/user/orders' }, { label: '订单详情' }, { label: '退款与售后' }]" />
    <HelpSteps :steps="buyerSteps" />
    <p>提交后，订单详情会显示退款状态和处理时间线。新申请的金额由系统按订单实付金额确定，不需要手工输入。</p>

    <h2 id="seller-handle">卖家如何处理</h2>
    <HelpPath :items="[{ label: '卖家后台', to: '/seller' }, { label: '退款售后', to: '/seller/refunds' }, { label: '订单详情' }]" />
    <HelpTable :columns="sellerColumns" :rows="sellerRows" caption="卖家可选的退款处理方式" />
    <HelpCallout title="“同意并退款”不可撤销" tone="danger">
      确认后系统会立即调用该订单原收款应用的 Credit 退款接口，按实付金额全额退回 LDC。操作前必须再次核对订单、买家和协商结果。
    </HelpCallout>

    <h2 id="status">看懂退款状态</h2>
    <HelpTable :columns="statusColumns" :rows="statusRows" caption="退款状态与下一步" />

    <h2 id="refund-exceptions">退款执行失败或结果待核实</h2>
    <ul>
      <li><strong>执行失败：</strong>页面已收到明确失败结果。卖家按提示检查原收款凭证、余额或订单状态后，可从订单详情重试；管理员也可在留下核对依据后安全重试。</li>
      <li><strong>结果待核实：</strong>请求可能已送达 Credit，但商城未获得可确认结果。为防止重复退款，页面不提供重试；双方应保留订单号并联系 LD 士多核实。</li>
      <li><strong>已转 Credit 处理：</strong>Credit 中的原订单已不再是 success 状态，LD 士多会结束本地退款流程。这不代表积分已退回，请到 Credit 核对争议状态、交易记录和余额。</li>
      <li>在结果明确前，卖家不要通过其他入口对同一订单重复操作，买家也不必重复提交申请。</li>
    </ul>

    <h2 id="credit-dispute">卖家拒绝后如何继续争议</h2>
    <p>如果卖家拒绝退款，双方后续协商仍无法解决，买家可通过“联系与反馈”提供订单号及证据，请求 LD 士多管理员核实并裁决，或前往 <a href="https://credit.linux.do" target="_blank" rel="noopener noreferrer">credit.linux.do</a> 查找原交易并发起争议，请求 Credit 平台介入。</p>
    <ol>
      <li>带上 LD 士多订单号、Credit 交易号和退款申请时间线。</li>
      <li>客观说明物品承诺、实际交付、问题和已经完成的协商。</li>
      <li>只提供支持事实的必要证据，隐去卡密、密码和无关个人信息。</li>
    </ol>
    <p>可同时阅读 <a href="https://credit.linux.do/docs/how-to-use#%E4%BA%89%E8%AE%AE%E5%A4%84%E7%90%86" target="_blank" rel="noopener noreferrer">Credit 争议处理说明</a>。LD 士多会保留本站退款申请与卖家响应记录，但 Credit 争议的受理和结果以 Credit 平台为准。</p>

    <div class="help-actions">
      <router-link to="/user/orders">查看我的订单</router-link>
      <router-link to="/seller/refunds" class="secondary">打开退款售后</router-link>
      <router-link to="/support" class="secondary">联系与反馈</router-link>
    </div>
  </div>
</template>

<script setup>
import HelpCallout from './HelpCallout.vue'
import HelpPath from './HelpPath.vue'
import HelpSteps from './HelpSteps.vue'
import HelpTable from './HelpTable.vue'

const buyerSteps = [
  { title: '可先联系卖家', description: '可通过 LINUX DO 私信协商，也可以直接申请退款。' },
  { title: '打开退款表单', description: '在订单详情的“退款与售后”中选择申请退款。' },
  { title: '说清原因', description: '选择最接近的原因，用 10–500 字写明实际问题，并如实标记是否已联系卖家。' },
  { title: '核对后提交', description: '确认页面显示的全额退款金额和订单号。', result: '卖家会收到新的退款待办。' }
]
const sellerColumns = [
  { key: 'action', label: '处理方式' },
  { key: 'when', label: '适用情况' },
  { key: 'result', label: '结果' }
]
const sellerRows = [
  { action: '联系买家 / 标记协商', when: '需要补充信息或希望先直接解决', result: '状态变为“协商中”，留下卖家备注' },
  { action: '拒绝退款', when: '核对后认为不符合退款约定', result: '必须填写具体理由，买家可查看并继续协商或争议' },
  { action: '同意并退款', when: '双方已确认应退回原订单全额', result: '立即调用 Credit 退款；成功后订单变为已退款' }
]
const statusColumns = [
  { key: 'status', label: '状态' },
  { key: 'meaning', label: '含义' },
  { key: 'next', label: '下一步' }
]
const statusRows = [
  { status: '待卖家处理', meaning: '申请已提交，等待卖家首次响应', next: '卖家联系、拒绝或同意' },
  { status: '协商中', meaning: '卖家已响应，双方还在核对事实', next: '在 LINUX DO 继续沟通，卖家最终决定' },
  { status: '退款中', meaning: '系统正在向 Credit 提交全额退款', next: '不要重复操作，等待结果' },
  { status: '已退款', meaning: 'Credit 已返回成功，订单和退款记录已完成', next: '买家到 Credit 余额或交易记录核对' },
  { status: '已拒绝', meaning: '卖家已给出拒绝理由', next: '继续协商；仍有争议时到 Credit 发起争议' },
  { status: '已转 Credit 处理', meaning: 'Credit 原订单已不是 success，本站已结束退款流程', next: '到 Credit 核对实际争议或退回结果' },
  { status: '执行失败 / 结果待核实', meaning: '退款未能正常确认', next: '按页面的差异化提示处理，待核实状态不要重试' }
]
</script>
