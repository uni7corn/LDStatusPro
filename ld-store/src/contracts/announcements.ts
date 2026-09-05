import { array, boolean, looseObject, nullable, number, optional, string } from 'valibot'
import { PaginationSchema } from './catalog'
export const AnnouncementItemSchema = looseObject({
  id: number(), title: string(), content: string(), mode: string(), contentType: string(), type: string(),
  enabled: boolean(), startsAt: nullable(number()), expiresAt: nullable(number()),
  summary: optional(string()), status: optional(string()), actionLabel: optional(string()), actionUrl: optional(string()),
  requiresAcknowledgement: optional(boolean()), contentVersion: optional(number()), reminderVersion: optional(number()),
  popupDismissKey: optional(string()), placements: optional(array(string()))
})
export const AnnouncementListSchema = looseObject({ items: array(AnnouncementItemSchema), pagination: optional(PaginationSchema), timestamp: number() })
export const AnnouncementDetailSchema = looseObject({ item: AnnouncementItemSchema, timestamp: number() })
export const AnnouncementStateSchema = looseObject({ items: array(looseObject({ announcementId: number(), reminderVersion: number(), dismissedUntil: nullable(number()), forever: boolean(), acknowledgedVersion: nullable(number()) })) })
