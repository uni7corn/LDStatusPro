import { array, boolean, looseObject, nullable, number, optional, string, type InferOutput } from 'valibot'

export const FulfillmentInfoSchema = looseObject({
  policyVersion: nullable(string()), source: nullable(string()), deadlineAt: nullable(string()), serverNow: string(),
  remainingSeconds: nullable(number()), canDeliver: boolean(), deliveryDisabledReason: nullable(string()),
  canProactivelyRefund: boolean(), ruleUrl: string()
})
export const FulfillmentPolicySchema = looseObject({ version: string(), enabled: boolean(), enabledAt: nullable(string()),
  deliveryHours: number(), offlineHours: number(), strikeWindowDays: number(), strikeThreshold: number(), restrictionHours: number(), ruleUrl: string() })
export const FulfillmentPenaltySchema = looseObject({ id: number(), startedAt: string(), endsAt: string(), releasedAt: nullable(string()) })
export const SellerFulfillmentSchema = looseObject({
  validCount: number(), threshold: number(), windowDays: number(), restrictionHours: number(), accepted: boolean(), enabled: boolean(),
  policyVersion: string(), activeRestriction: nullable(FulfillmentPenaltySchema), restrictions: array(FulfillmentPenaltySchema),
  history: array(looseObject({ id: number(), orderNo: string(), occurredAt: string(), penaltyId: nullable(number()),
    exemptReason: nullable(string()), revokedAt: nullable(string()), revokeReason: optional(nullable(string())) })), ruleUrl: string(), supportUrl: string()
})
export type FulfillmentInfo = InferOutput<typeof FulfillmentInfoSchema>
export type SellerFulfillment = InferOutput<typeof SellerFulfillmentSchema>
