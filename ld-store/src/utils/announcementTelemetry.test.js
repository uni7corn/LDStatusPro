// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
const send = vi.hoisted(() => vi.fn())
vi.mock('@/services/announcementService', () => ({ sendAnnouncementEvents: send }))
afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetModules(); send.mockReset() })
it('requires sustained visibility, retries the same event ID and clears account context', async () => {
  vi.useFakeTimers(); vi.stubEnv('PROD', true)
  let callback
  vi.stubGlobal('IntersectionObserver', class { constructor(cb) {callback=cb} observe(){} disconnect(){} })
  const telemetry = await import('./announcementTelemetry')
  const element = document.createElement('div'), binding = { value:{item:{id:1,contentVersion:1,reminderVersion:1},placement:'storefront'} }
  send.mockResolvedValueOnce({success:false}).mockResolvedValue({success:true})
  telemetry.announcementImpression.mounted(element,binding)
  callback([{intersectionRatio:.5}]); await vi.advanceTimersByTimeAsync(900)
  callback([{intersectionRatio:.1}]); await vi.advanceTimersByTimeAsync(1000)
  await telemetry.flushAnnouncementEvents(); expect(send).not.toHaveBeenCalled()
  callback([{intersectionRatio:.8}]); await vi.advanceTimersByTimeAsync(1100)
  await telemetry.flushAnnouncementEvents(); await telemetry.flushAnnouncementEvents()
  expect(send.mock.calls[0][0][0].eventId).toBe(send.mock.calls[1][0][0].eventId)
  telemetry.trackAnnouncement(binding.value.item,'close','storefront'); telemetry.setAnnouncementTelemetryIdentity('another')
  await telemetry.flushAnnouncementEvents(); expect(send).toHaveBeenCalledTimes(2)
  telemetry.announcementImpression.unmounted(element)
})

it('excludes explicitly marked synthetic sessions',async()=>{
  vi.stubEnv('PROD',true)
  vi.stubGlobal('location',{search:'?context_synthetic=true'})
  const telemetry=await import('./announcementTelemetry')
  telemetry.trackAnnouncement({id:1},'open','detail')
  await telemetry.flushAnnouncementEvents()
  expect(send).not.toHaveBeenCalled()
})
