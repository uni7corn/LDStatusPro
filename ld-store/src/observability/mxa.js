const MXA_SCRIPT_ID = 'MXA_COLLECT'
const MXA_SCRIPT_URL = 'https://mxana.tacool.com/sdk.js'
const MXA_SITE_ID = 'c2-9FYYP0Vm'

let initializationPromise = null

export function initializeMxaAnalytics(
  documentLike = globalThis.document,
  windowLike = globalThis.window
) {
  if (!documentLike?.head || !windowLike) return Promise.resolve(null)
  if (initializationPromise) return initializationPromise

  initializationPromise = new Promise((resolve) => {
    const initialize = () => {
      try {
        windowLike.MXA?.init({ id: MXA_SITE_ID })
        resolve(windowLike.MXA || null)
      } catch {
        resolve(null)
      }
    }

    const existing = documentLike.getElementById(MXA_SCRIPT_ID)
    if (existing) {
      if (windowLike.MXA) initialize()
      else {
        existing.addEventListener('load', initialize, { once: true })
        existing.addEventListener('error', () => resolve(null), { once: true })
      }
      return
    }

    const script = documentLike.createElement('script')
    script.id = MXA_SCRIPT_ID
    script.src = MXA_SCRIPT_URL
    script.async = true
    script.charset = 'UTF-8'
    script.addEventListener('load', initialize, { once: true })
    script.addEventListener('error', () => resolve(null), { once: true })
    documentLike.head.append(script)
  })

  return initializationPromise
}
