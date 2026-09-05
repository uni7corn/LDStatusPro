import { api } from '@/utils/api'
import { AnnouncementListSchema, AnnouncementDetailSchema, AnnouncementStateSchema } from '@/contracts/announcements'
import { validateServiceResult, withServiceFailure } from '@/services/serviceContract'
const base = '/api/shop/announcements'
export function fetchAnnouncementsRequest(signal?: AbortSignal, placement = 'storefront') {
  return withServiceFailure(async () => validateServiceResult(await api.get(`${base}?placement=${encodeURIComponent(placement)}`, { signal }), AnnouncementListSchema, base, 'AnnouncementList'), '加载公告失败')
}
export function fetchAnnouncementCenter(query: { page?: number; search?: string; status?: string } = {}, signal?: AbortSignal) {
  const params = new URLSearchParams({ page: String(query.page || 1), pageSize: '20', search: query.search || '', status: query.status || '' })
  return withServiceFailure(async () => validateServiceResult(await api.get(`${base}/center?${params}`, { signal }), AnnouncementListSchema, base, 'AnnouncementCenter'), '加载公告失败')
}
export function fetchAnnouncementDetail(id: string, signal?: AbortSignal) {
  return withServiceFailure(async () => validateServiceResult(await api.get(`${base}/${encodeURIComponent(id)}`, { signal }), AnnouncementDetailSchema, base, 'AnnouncementDetail'), '加载公告失败')
}
export function fetchAnnouncementStates() {
  return withServiceFailure(async () => validateServiceResult(await api.get(`${base}/states`), AnnouncementStateSchema, base, 'AnnouncementStates'), '同步提醒状态失败')
}
export function saveAnnouncementState(id: number, payload: { reminderVersion: number; mode: string }) {
  return api.put(`${base}/${id}/state`, payload)
}
export function acknowledgeAnnouncement(id: number, contentVersion: number) {
  return api.post(`${base}/${id}/acknowledge`, { contentVersion })
}
export function sendAnnouncementEvents(events: Record<string, string | number>[]) { return api.post(`${base}/events`, { events }) }
