// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
const { fetchRequest } = vi.hoisted(() => ({ fetchRequest: vi.fn() }))
vi.mock('@/services/announcementService', () => ({ fetchAnnouncementsRequest: fetchRequest }))
afterEach(() => { vi.useRealTimers(); vi.resetModules(); fetchRequest.mockReset() })
it('expires locally and retains valid content after failed refresh', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-09-05T00:00:00Z'))
  const timestamp = Date.now()
  fetchRequest.mockResolvedValue({ success: true, data: { timestamp, items: [
    { id: 1, content: '短期', expiresAt: timestamp + 2000 }, { id: 2, content: '长期' }
  ] } })
  const state = (await import('./useAnnouncement')).useAnnouncement()
  state.startAnnouncements()
  await state.fetchAnnouncements()
  expect(state.announcementItems.value).toHaveLength(2)
  await vi.advanceTimersByTimeAsync(2100)
  expect(state.announcementItems.value.map(x => x.id)).toEqual([2])
  fetchRequest.mockRejectedValue(new Error('offline'))
  await vi.advanceTimersByTimeAsync(30000)
  expect(state.announcementError.value).toBe('offline')
  expect(state.announcementItems.value.map(x => x.id)).toEqual([2])
  state.stopAnnouncements()
  const calls = fetchRequest.mock.calls.length
  await vi.advanceTimersByTimeAsync(60000)
  expect(fetchRequest).toHaveBeenCalledTimes(calls)
})
it('discards delayed responses after an audience context change', async () => {
  let resolveOld
  fetchRequest.mockImplementationOnce(() => new Promise(resolve => {resolveOld=resolve}))
  const state = (await import('./useAnnouncement')).useAnnouncement()
  const old = state.fetchAnnouncements(true)
  state.configureAnnouncements('guest', 'seller')
  fetchRequest.mockResolvedValue({success:true,data:{timestamp:Date.now(),items:[{id:2,content:'卖家位置'}]}})
  await state.fetchAnnouncements(true)
  resolveOld({success:true,data:{timestamp:Date.now(),items:[{id:1,content:'旧位置'}]}})
  await old
  expect(state.announcementItems.value.map(item=>item.id)).toEqual([2])
})
