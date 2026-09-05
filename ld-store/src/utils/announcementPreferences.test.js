// @vitest-environment jsdom
import { beforeEach, expect, it, vi } from 'vitest'
const server = vi.hoisted(() => ({ fetch: vi.fn(), save: vi.fn() }))
vi.mock('@/services/announcementService', () => ({fetchAnnouncementStates:server.fetch,saveAnnouncementState:server.save}))
import { setAnnouncementPreferenceIdentity, syncAnnouncementPreferences, dismissAnnouncement, isAnnouncementDismissed, markPopupShown, sessionHasPopup } from './announcementPreferences'
beforeEach(() => { localStorage.clear(); sessionStorage.clear() })
it('separates accounts and reminder versions, and caps one popup per tab', () => {
  const item = { id: 7, reminderVersion: 1 }
  dismissAnnouncement('a', item, 'forever')
  expect(isAnnouncementDismissed('a', item)).toBe(true)
  expect(isAnnouncementDismissed('b', item)).toBe(false)
  expect(isAnnouncementDismissed('a', { ...item, reminderVersion: 2 })).toBe(false)
  markPopupShown('a')
  expect(sessionHasPopup('a')).toBe(true)
  expect(sessionHasPopup('b')).toBe(false)
})
it('keeps old unscoped suppression local and works when storage access is denied', () => {
  const item={id:99,reminderVersion:1,popupDismissKey:'legacy-test'}
  localStorage.setItem('ld-shop-popup-read:legacy-test','permanent')
  expect(isAnnouncementDismissed('guest',item)).toBe(true)
  expect(isAnnouncementDismissed('guest',{...item,reminderVersion:2})).toBe(false)
  const descriptor=Object.getOwnPropertyDescriptor(window,'localStorage')
  Object.defineProperty(window,'localStorage',{configurable:true,get(){throw new Error('blocked')}})
  try { dismissAnnouncement('guest',{id:100},'forever'); expect(isAnnouncementDismissed('guest',{id:100})).toBe(true) }
  finally {Object.defineProperty(window,'localStorage',descriptor)}
})

it('loads account suppression from another device without uploading unscoped legacy records', async () => {
  setAnnouncementPreferenceIdentity('device-account')
  server.fetch.mockResolvedValue({success:true,data:{items:[{announcementId:72,reminderVersion:1,forever:true,dismissedUntil:null}]}})
  expect(await syncAnnouncementPreferences('device-account')).toBe(true)
  expect(isAnnouncementDismissed('device-account',{id:72})).toBe(true)
  expect(isAnnouncementDismissed('other-account',{id:72})).toBe(false)
  expect(server.save).not.toHaveBeenCalled()
  setAnnouncementPreferenceIdentity('guest')
})
