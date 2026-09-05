// @vitest-environment jsdom
/* global document, localStorage, KeyboardEvent, setTimeout */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { useFulfillmentReminder } from '../src/composables/useFulfillmentReminder'
import FulfillmentRuleDialog from '../src/components/seller/FulfillmentRuleDialog.vue'
import SellerFulfillmentPanel from '../src/components/seller/SellerFulfillmentPanel.vue'
import Publish from '../src/views/Publish.vue'
import { writeProductPublishDraft, readProductPublishDraft } from '../src/utils/productPublishDraft'

const m = vi.hoisted(() => ({ policy: vi.fn(), seller: vi.fn(), ack: vi.fn(), create: vi.fn(), categories: vi.fn(), merchant: vi.fn(), push: vi.fn(), confirm: vi.fn(), user: null, toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), loading: vi.fn(), update: vi.fn(), close: vi.fn() } }))
vi.mock('@/services/shop/fulfillmentService', () => ({ fetchFulfillmentPolicy: m.policy, fetchSellerFulfillment: m.seller, acknowledgeFulfillment: m.ack }))
vi.mock('@/stores/user', () => ({ useUserStore: () => m.user }))
vi.mock('@/stores/catalog', () => ({ useCatalogStore: () => ({ fetchCategories: m.categories }) }))
vi.mock('@/stores/inventory', () => ({ useInventoryStore: () => ({ fetchMerchantConfig: m.merchant, createProduct: m.create }) }))
vi.mock('@/composables/useToast', () => ({ useToast: () => m.toast }))
vi.mock('@/composables/useDialog', () => ({ useDialog: () => ({ confirm: m.confirm }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: m.push }), useRoute: () => ({ query: {} }), onBeforeRouteLeave: vi.fn() }))
vi.mock('@/utils/productImageValidation', async original => ({ ...await original(), preloadProductImage: vi.fn().mockResolvedValue(undefined) }))
const rules = { version: 'shipment-72h-v1', enabled: true, deliveryHours: 72, offlineHours: 48, strikeWindowDays: 30, strikeThreshold: 3, restrictionHours: 168, ruleUrl: '/docs/shipping-deadline' }
const seller = overrides => ({ enabled: true, accepted: true, policyVersion: rules.version, validCount: 0, threshold: 3, windowDays: 30, restrictionHours: 168, activeRestriction: null, history: [], restrictions: [], ruleUrl: rules.ruleUrl, supportUrl: '/support', ...overrides })
const ok = data => ({ success: true, data })
const fail = (error = '请求失败', errorCode) => ({ success: false, error, errorCode })
const restriction = { id: 1, startedAt: '2026-09-01T00:00:00Z', endsAt: '2026-09-08T00:00:00Z', releasedAt: null }
let wrappers = []
const keep = wrapper => { wrappers.push(wrapper); return wrapper }
const link = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const editor = { name: 'ProductEditorForm', props: ['modelValue'], emits: ['update:modelValue'], template: '<section class="editor-stub" />' }
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear()
  m.user = reactive({ currentUser: { id: 18, site: 'linux.do' } })
  m.policy.mockResolvedValue(ok({ ...rules })); m.seller.mockResolvedValue(ok(seller())); m.ack.mockResolvedValue(ok(seller()))
  m.categories.mockResolvedValue(ok({ categories: [{ id: 3, name: '工具' }] }))
  m.merchant.mockResolvedValue(ok({ configured: true, isActive: true, isVerified: true }))
  m.confirm.mockResolvedValue(true); m.create.mockResolvedValue(ok({ id: 1 }))
})
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers = []; document.body.innerHTML = ''; document.body.style.overflow = ''; localStorage.clear() })
function controller() {
  let reminder
  keep(mount(defineComponent({ setup() { reminder = useFulfillmentReminder(() => String(m.user.currentUser.id)); return () => null } })))
  return reminder
}
async function page({ guide = false, ...props } = {}) {
  if (!guide) localStorage.setItem('ld_store_publish_guide_seen', 'true')
  const wrapper = keep(mount(Publish, { attachTo: document.body, props, global: { stubs: { RouterLink: link, ProductEditorForm: editor, BuyRequestEditorForm: true, PurchaseLimitSelector: true, SellerStickySummary: { template: '<aside><slot /><slot name="action" /></aside>' }, transition: false } } }))
  await flushPromises(); return wrapper
}
const form = w => w.findComponent(editor).props('modelValue')
async function updateForm(w, values) { w.findComponent(editor).vm.$emit('update:modelValue', { ...form(w), ...values }); await flushPromises() }
async function chooseNormal(w) { await w.findAll('[role="radio"]')[1].trigger('click'); await flushPromises() }
async function confirmDialog(w) { w.findComponent(FulfillmentRuleDialog).vm.$emit('confirm'); await flushPromises() }
const visibleDialog = () => document.querySelector('.fulfillment-dialog-panel')
const validForm = { name: '测试普通物品', description: '这是足够完整的测试物品描述内容。', price: '10', stock: '2', imageUrl: 'https://images.example.com/item.png' }

describe('per-flow fulfillment confirmation', () => {
  it('accepts on the server only when needed and resets the reminder for each flow', async () => {
    m.seller.mockResolvedValue(ok(seller({ accepted: false })))
    const r = controller(), first = r.request()
    await flushPromises(); expect(m.ack).not.toHaveBeenCalled()
    await r.confirm(); expect(await first).toBe(true)
    expect(m.ack).toHaveBeenCalledWith(rules.version)
    expect(await r.request()).toBe(true); expect(m.policy).toHaveBeenCalledTimes(1)
    r.reset(); m.seller.mockResolvedValue(ok(seller()))
    const next = r.request(); await flushPromises()
    expect(r.dialogProps.value.open).toBe(true)
    await r.confirm(); expect(await next).toBe(true); expect(m.ack).toHaveBeenCalledTimes(1)
  })
  it('deduplicates pending requests, and cancellation does not count as confirmation', async () => {
    const r = controller(), first = r.request()
    expect(r.request()).toBe(first); await flushPromises(); r.cancel(); expect(await first).toBe(false)
    const next = r.request(); await flushPromises(); expect(r.dialogProps.value.open).toBe(true)
    r.cancel(); expect(await next).toBe(false)
  })
  it('ignores stale requests when the account changes', async () => {
    let resolve
    m.policy.mockReturnValueOnce(new Promise(r => { resolve = r }))
    const r = controller(), pending = r.request()
    m.user.currentUser.id = 19; expect(await pending).toBe(false)
    resolve(ok(rules)); await flushPromises(); expect(r.dialogProps.value.open).toBe(false)
  })
  it('rechecks acceptance and policy version at submission', async () => {
    const r = controller(), first = r.request()
    await flushPromises(); await r.confirm(); await first
    expect(await r.request({ refresh: true })).toBe(true)
    m.policy.mockResolvedValue(ok({ ...rules, version: 'v2' })); m.seller.mockResolvedValue(ok(seller({ policyVersion: 'v2', accepted: false })))
    const changed = r.request({ refresh: true }); await flushPromises()
    expect(r.dialogProps.value.open).toBe(true)
    m.ack.mockResolvedValue(ok(seller({ policyVersion: 'v2' })))
    await r.confirm(); expect(await changed).toBe(true); expect(m.ack).toHaveBeenCalledWith('v2')
  })
  it('keeps loading and acknowledgement failures retryable', async () => {
    m.policy.mockResolvedValueOnce(fail('规则加载失败')); m.seller.mockResolvedValue(ok(seller({ accepted: false })))
    const r = controller(), pending = r.request(); await flushPromises()
    expect(r.dialogProps.value.error).toBe('规则加载失败'); await r.confirm(); expect(m.ack).not.toHaveBeenCalled()
    r.retry(); await flushPromises(); m.ack.mockResolvedValueOnce(fail('确认失败')); await r.confirm()
    expect(r.dialogProps.value.open).toBe(true); expect(r.dialogProps.value.error).toBe('确认失败')
    r.retry(); await flushPromises(); await r.confirm(); expect(await pending).toBe(true)
  })
  it('refreshes a version mismatch without silently accepting the new version', async () => {
    m.seller.mockResolvedValue(ok(seller({ accepted: false })))
    const r = controller(), pending = r.request(); await flushPromises()
    m.ack.mockResolvedValueOnce(fail('规则更新', 'POLICY_VERSION_MISMATCH'))
    m.policy.mockResolvedValue(ok({ ...rules, version: 'v2' })); m.seller.mockResolvedValue(ok(seller({ policyVersion: 'v2', accepted: false })))
    await r.confirm(); expect(r.dialogProps.value.policy.version).toBe('v2'); expect(r.dialogProps.value.open).toBe(true)
    expect(m.ack).toHaveBeenCalledTimes(1); r.cancel(); await pending
  })
  it('skips disabled rules and blocks active restrictions', async () => {
    const r = controller(); m.policy.mockResolvedValueOnce(ok({ ...rules, enabled: false })); m.seller.mockResolvedValueOnce(fail())
    expect(await r.request()).toBe(true); expect(m.ack).not.toHaveBeenCalled()
    m.seller.mockResolvedValue(ok(seller({ activeRestriction: restriction })))
    const pending = r.request(); await flushPromises(); await r.confirm()
    expect(r.dialogProps.value.open).toBe(true); r.cancel(); expect(await pending).toBe(false)
  })
})

describe('publish integration', () => {
  it('defaults to CDK with the accessible type selector first and preserves the universal guide', async () => {
    const w = await page({ guide: true }), radios = w.findAll('[role="radio"]')
    expect(radios[0].text()).toContain('CDK 物品'); expect(radios[1].text()).toContain('普通物品')
    expect(radios[0].attributes('aria-checked')).toBe('true')
    expect(w.html().indexOf('product-type-section')).toBeLessThan(w.html().indexOf('editor-stub'))
    expect(document.body.textContent).toContain('发布前必读'); expect(document.body.textContent).toContain('不再提示')
    expect(m.policy).not.toHaveBeenCalled()
  })
  it('preserves CDK secrets and shared/test configuration when selection is cancelled', async () => {
    const w = await page(); await updateForm(w, { cdkCodes: 'SECRET', sharedCdkEnabled: true, sharedCdkCode: 'SHARED', isTestMode: true })
    await chooseNormal(w); expect(form(w).productType).toBe('cdk')
    w.findComponent(FulfillmentRuleDialog).vm.$emit('cancel'); await flushPromises()
    expect(form(w)).toMatchObject({ productType: 'cdk', cdkCodes: 'SECRET', sharedCdkEnabled: true, sharedCdkCode: 'SHARED', isTestMode: true })
    expect(m.create).not.toHaveBeenCalled()
  })
  it('only reminds once during repeated type switches', async () => {
    const w = await page(); await chooseNormal(w); await confirmDialog(w)
    expect(form(w).productType).toBe('normal')
    await w.findAll('[role="radio"]')[0].trigger('click'); await chooseNormal(w)
    expect(w.findComponent(FulfillmentRuleDialog).props('open')).toBe(false)
    expect(m.policy).toHaveBeenCalledTimes(1); expect(m.create).not.toHaveBeenCalled()
  })
  it('supports radio arrow keys and returns focus to the selected option', async () => {
    const w = await page(); await w.findAll('[role="radio"]')[0].trigger('keydown', { key: 'ArrowRight' })
    await flushPromises(); await confirmDialog(w)
    expect(form(w).productType).toBe('normal'); expect(document.activeElement.getAttribute('aria-checked')).toBe('true')
    await w.findAll('[role="radio"]')[1].trigger('keydown', { key: 'Home' }); await flushPromises()
    expect(form(w).productType).toBe('cdk')
  })
  it('queues a restored normal draft after the guide and preserves the do-not-show preference', async () => {
    writeProductPublishDraft(m.user.currentUser, { productType: 'normal', name: '已保存物品', stock: '2' })
    const w = await page({ guide: true }); expect(form(w).productType).toBe('normal'); expect(m.policy).not.toHaveBeenCalled()
    const remember = document.querySelector('.guide-modal-remember input'); remember.checked = true
    remember.dispatchEvent(new document.defaultView.Event('change', { bubbles: true }))
    document.querySelector('.guide-btn-secondary').click()
    await new Promise(resolve => setTimeout(resolve, 80)); await flushPromises()
    expect(localStorage.getItem('ld_store_publish_guide_seen')).toBe('true')
    expect(document.querySelector('.guide-modal-overlay')).toBeNull(); expect(visibleDialog()).not.toBeNull()
    w.findComponent(FulfillmentRuleDialog).vm.$emit('cancel'); await flushPromises()
    expect(form(w)).toMatchObject({ productType: 'normal', name: '已保存物品', stock: '2' })
  })
  it('preserves CDK draft type, omits secrets and resets a discarded draft to CDK', async () => {
    writeProductPublishDraft(m.user.currentUser, { productType: 'cdk', name: '卡密草稿', cdkCodes: 'SECRET' })
    const w = await page(); expect(form(w)).toMatchObject({ productType: 'cdk', name: '卡密草稿', cdkCodes: '' })
    await chooseNormal(w); await confirmDialog(w)
    await w.find('.draft-discard-button').trigger('click'); await flushPromises()
    expect(form(w).productType).toBe('cdk'); expect(readProductPublishDraft(m.user.currentUser).draft).toBeNull()
    await chooseNormal(w); expect(w.findComponent(FulfillmentRuleDialog).props('open')).toBe(true)
  })
  it('does not publish on confirmation; a later submit rechecks the server', async () => {
    const w = await page(); await updateForm(w, validForm); await chooseNormal(w)
    expect(m.create).not.toHaveBeenCalled(); await confirmDialog(w); expect(m.create).not.toHaveBeenCalled()
    await w.find('form.publish-form').trigger('submit'); await flushPromises()
    expect(m.create).toHaveBeenCalledTimes(1); expect(m.create.mock.calls[0][0].productType).toBe('normal')
    expect(m.seller).toHaveBeenCalledTimes(2)
  })
  it('requires a new publish click when submission discovers an updated rule version', async () => {
    const w = await page(); await updateForm(w, validForm); await chooseNormal(w); await confirmDialog(w)
    m.policy.mockResolvedValue(ok({ ...rules, version: 'v2' })); m.seller.mockResolvedValue(ok(seller({ policyVersion: 'v2' })))
    await w.find('form.publish-form').trigger('submit'); await flushPromises()
    expect(w.findComponent(FulfillmentRuleDialog).props('open')).toBe(true)
    await confirmDialog(w); expect(m.create).not.toHaveBeenCalled()
    await w.find('form.publish-form').trigger('submit'); await flushPromises()
    expect(m.create).toHaveBeenCalledTimes(1)
  })
  it('keeps a cancelled normal draft blocked at submission until it is confirmed', async () => {
    writeProductPublishDraft(m.user.currentUser, { ...validForm, productType: 'normal', categoryId: 3 })
    const w = await page(); w.findComponent(FulfillmentRuleDialog).vm.$emit('cancel'); await flushPromises()
    await w.find('form.publish-form').trigger('submit'); await flushPromises()
    expect(w.findComponent(FulfillmentRuleDialog).props('open')).toBe(true)
    expect(m.create).not.toHaveBeenCalled(); await confirmDialog(w); expect(m.create).not.toHaveBeenCalled()
  })
  it('handles server rejection without retrying product creation after confirmation', async () => {
    const w = await page(); await updateForm(w, validForm); await chooseNormal(w); await confirmDialog(w)
    m.create.mockResolvedValueOnce(fail('未确认规则', 'FULFILLMENT_RULE_NOT_ACCEPTED'))
    await w.find('form.publish-form').trigger('submit'); await flushPromises()
    expect(w.findComponent(FulfillmentRuleDialog).props('open')).toBe(true)
    await confirmDialog(w); expect(m.create).toHaveBeenCalledTimes(1); expect(form(w).name).toBe(validForm.name)
  })
  it('does not request normal rules in the buy-request flow', async () => {
    writeProductPublishDraft(m.user.currentUser, { productType: 'normal', name: '普通草稿' })
    const w = await page({ initialMode: 'buy', lockedMode: true })
    expect(w.find('[role="radiogroup"]').exists()).toBe(false); expect(m.policy).not.toHaveBeenCalled()
  })
})

describe('dialog accessibility and overview', () => {
  it('requires explicit acceptance, traps focus and restores it after closing', async () => {
    const trigger = document.createElement('button'); document.body.append(trigger); trigger.focus()
    const w = keep(mount(FulfillmentRuleDialog, { attachTo: document.body, props: { open: false, loading: false, busy: false, error: '', state: seller({ accepted: false }), policy: rules } }))
    await w.setProps({ open: true }); await flushPromises(); const dialog = visibleDialog()
    expect(dialog.getAttribute('aria-modal')).toBe('true'); expect(document.body.style.overflow).toBe('hidden')
    const primary = dialog.querySelector('.rule-primary'); expect(primary.disabled).toBe(true)
    const checkbox = dialog.querySelector('input'); checkbox.checked = true; checkbox.dispatchEvent(new document.defaultView.Event('change', { bubbles: true })); await flushPromises()
    expect(primary.disabled).toBe(false); primary.focus(); primary.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(dialog.querySelector('.rule-close'))
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); expect(w.emitted('cancel')).toHaveLength(1)
    await w.setProps({ open: false }); await flushPromises(); expect(document.body.style.overflow).toBe(''); expect(document.activeElement).toBe(trigger)
    await w.setProps({ open: true }); await flushPromises(); expect(visibleDialog().querySelector('input').checked).toBe(false)
  })
  it('hides healthy overview alerts and displays actionable records or restrictions', async () => {
    const w = keep(mount(SellerFulfillmentPanel, { props: { placement: 'summary', state: seller() }, global: { stubs: { RouterLink: link } } }))
    expect(w.find('aside').exists()).toBe(false); await w.setProps({ state: seller({ validCount: 2 }) }); expect(w.text()).toContain('再有 1 笔')
    await w.setProps({ state: seller({ activeRestriction: restriction }) }); expect(w.text()).toContain('新增交易受限至'); expect(w.text()).toContain('已有订单仍可交付')
  })
  it('keeps history and acknowledgement behind a collapsed bottom entry', () => {
    const w = keep(mount(SellerFulfillmentPanel, { props: { placement: 'details', state: seller({ accepted: false, history: [{ id: 1, orderNo: 'ORDER-1', occurredAt: '2026-09-01T00:00:00Z', revokedAt: '2026-09-02T00:00:00Z', revokeReason: '已核实误判' }] }) }, global: { stubs: { RouterLink: link } } }))
    expect(w.find('details').element.open).toBe(false); expect(w.text()).toContain('阅读并确认发货规则')
    expect(w.text()).toContain('已撤销'); expect(w.text()).toContain('已核实误判'); expect(w.find('.fulfillment-history').element.open).toBe(false)
  })
})
