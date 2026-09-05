// @vitest-environment jsdom
import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import Popup from './AnnouncementPopup.vue'
const fixtures = vi.hoisted(() => ({ state:null, account:null, route:null }))
vi.mock('@/composables/useAnnouncement', () => ({ useAnnouncement:()=>fixtures.state }))
vi.mock('@/stores/user', () => ({ useUserStore:()=>fixtures.account }))
vi.mock('vue-router', () => ({ useRoute:()=>fixtures.route }))
vi.mock('@/utils/announcementTelemetry', () => ({ announcementImpression:{}, trackAnnouncement:vi.fn() }))
afterEach(()=>{document.body.innerHTML='';document.body.style.overflow='';sessionStorage.clear();localStorage.clear()})
it('opens with already loaded data, supports Escape and never opens a second popup in the same tab session',async()=>{
  HTMLDialogElement.prototype.showModal=function(){this.open=true}
  HTMLDialogElement.prototype.close=function(){this.open=false}
  fixtures.state={announcementItems:ref([{id:1,mode:'popup',title:'规则',content:'正文'},{id:2,mode:'popup',title:'第二条',content:'正文'}]),announcementPreferencesReady:ref(true)}
  fixtures.account={sessionReady:true,isLoggedIn:false,currentUser:null};fixtures.route={name:'Home',meta:{}}
  const wrapper=mount(Popup,{attachTo:document.body,global:{stubs:{RouterLink:{template:'<a><slot /></a>'}}}})
  await flushPromises()
  const dialog=document.querySelector('dialog')
  expect(dialog.open).toBe(true)
  expect(document.activeElement.id).toBe('announcement-popup-title')
  dialog.dispatchEvent(new Event('cancel',{cancelable:true}))
  await flushPromises()
  expect(dialog.open).toBe(false)
  expect(document.body.style.overflow).toBe('')
  wrapper.unmount()
  const remount=mount(Popup,{attachTo:document.body,global:{stubs:{RouterLink:true}}})
  await flushPromises();expect(document.querySelector('dialog').open).toBe(false);remount.unmount()
})
