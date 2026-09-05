import type { BaseIssue, BaseSchema } from 'valibot'
import { validateApiResult } from '@/contracts/apiContract'
import type { ApiFailure, ApiResult } from '@/utils/api'

type ContractSchema = BaseSchema<unknown, unknown, BaseIssue<unknown>>

export function validateServiceResult<TSchema extends ContractSchema>(
  result: ApiResult<unknown>,
  schema: TSchema,
  endpoint: string,
  schemaName: string
) {
  return validateApiResult(result, schema, { endpoint, schemaName })
}

export function serviceFailure(error: unknown, fallback: string): ApiFailure {
  return {
    success: false,
    status: 0,
    error: error instanceof Error ? error.message || fallback : fallback,
    aborted: false,
    kind: 'network'
  }
}

export async function withServiceFailure<T>(
  operation: () => Promise<ApiResult<T>>,
  fallback: string
): Promise<ApiResult<T>> {
  try {
    return await operation()
  } catch (error) {
    return serviceFailure(error, fallback)
  }
}
