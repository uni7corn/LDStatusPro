import { ref } from 'vue'
import type { ProductComment, ProductCommentReply } from '@/contracts/catalog'

type CommentRecord = ProductComment & Record<string, unknown>
type CommentReplyRecord = ProductCommentReply & Record<string, unknown>

interface CommentPagination {
  total: number
  page: number
  pageSize: number
  totalPages: number
}

interface CommentSummary {
  averageRating: number
  ratedCount: number
  favoriteCount: number
  visibleCommentCount: number
  visibleReplyCount: number
}

export interface ProductCommentRequest {
  signal: AbortSignal
  requestId: number
}

export function useProductComments() {
  const active = ref(false)
  const loading = ref(false)
  const commentList = ref<CommentRecord[]>([])
  const commentEnabled = ref(false)
  const commentDisabledReason = ref('该物品暂未开启评论')
  const commentPagination = ref<CommentPagination>({ total: 0, page: 1, pageSize: 10, totalPages: 0 })
  const commentSummary = ref<CommentSummary>({
    averageRating: 0,
    ratedCount: 0,
    favoriteCount: 0,
    visibleCommentCount: 0,
    visibleReplyCount: 0
  })
  const viewerHasPurchased = ref(false)
  const viewerHasRated = ref(false)
  const viewerRatingValue = ref<number | null>(null)
  const commentDraft = ref('')
  const commentRatingDraft = ref<number | null>(null)
  const commentSubmitting = ref(false)
  const commentActionMenuId = ref<number | null>(null)
  const commentDeletingId = ref<number | null>(null)
  const commentReportingId = ref<number | null>(null)
  const showCommentReportModal = ref(false)
  const commentReportReason = ref('')
  const commentReportSubmitting = ref(false)
  const commentReportTarget = ref<CommentRecord | null>(null)
  const commentVotingMap = ref<Record<number, boolean>>({})
  const commentReplyComposerIdSet = ref<Set<number>>(new Set())
  const commentReplyMap = ref<Record<number, CommentReplyRecord[]>>({})
  const commentReplyPaginationMap = ref<Record<number, CommentPagination>>({})
  const commentReplyLoadingMap = ref<Record<number, boolean>>({})
  const commentReplySubmittingMap = ref<Record<number, boolean>>({})
  const commentReplyDraftMap = ref<Record<number, string>>({})
  let nextRequestId = 0
  const controllers = new Map<string, AbortController>()
  const requestIds = new Map<string, number>()

  function activate() {
    active.value = true
  }

  function deactivate() {
    active.value = false
    loading.value = false
    for (const controller of controllers.values()) controller.abort('caller')
    controllers.clear()
    requestIds.clear()
    commentReplyLoadingMap.value = {}
  }

  function beginRequest(scope: string): ProductCommentRequest {
    controllers.get(scope)?.abort('caller')
    const controller = new AbortController()
    controllers.set(scope, controller)
    const currentRequestId = ++nextRequestId
    requestIds.set(scope, currentRequestId)
    if (scope === 'comments') loading.value = true
    return { signal: controller.signal, requestId: currentRequestId }
  }

  function ownsRequest(scope: string, request: ProductCommentRequest): boolean {
    return !request.signal.aborted
      && requestIds.get(scope) === request.requestId
      && controllers.get(scope)?.signal === request.signal
  }

  function isCurrent(scope: string, request: ProductCommentRequest): boolean {
    return active.value && ownsRequest(scope, request)
  }

  function finishRequest(scope: string, request: ProductCommentRequest) {
    if (controllers.get(scope)?.signal === request.signal) {
      controllers.delete(scope)
      requestIds.delete(scope)
      if (scope === 'comments') loading.value = false
    }
  }

  return {
    active,
    loading,
    commentList,
    commentEnabled,
    commentDisabledReason,
    commentPagination,
    commentSummary,
    viewerHasPurchased,
    viewerHasRated,
    viewerRatingValue,
    commentDraft,
    commentRatingDraft,
    commentSubmitting,
    commentActionMenuId,
    commentDeletingId,
    commentReportingId,
    showCommentReportModal,
    commentReportReason,
    commentReportSubmitting,
    commentReportTarget,
    commentVotingMap,
    commentReplyComposerIdSet,
    commentReplyMap,
    commentReplyPaginationMap,
    commentReplyLoadingMap,
    commentReplySubmittingMap,
    commentReplyDraftMap,
    activate,
    deactivate,
    beginRequest,
    ownsRequest,
    isCurrent,
    finishRequest
  }
}
