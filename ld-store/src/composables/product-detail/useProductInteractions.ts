import { ref } from 'vue'

interface ProductInteractionOptions {
  hasOpenModal: () => boolean
  onEscape: (event: KeyboardEvent) => void
  onDocumentClick: (event: MouseEvent) => void
}

export function useProductInteractions(options: ProductInteractionOptions) {
  const active = ref(false)

  function syncModalState() {
    if (typeof document === 'undefined') return
    const opened = active.value && options.hasOpenModal()
    document.body.style.overflow = opened ? 'hidden' : ''
    document.removeEventListener('keydown', options.onEscape)
    if (opened) document.addEventListener('keydown', options.onEscape)
  }

  function activate() {
    if (active.value || typeof document === 'undefined') return
    active.value = true
    document.addEventListener('click', options.onDocumentClick)
    syncModalState()
  }

  function deactivate() {
    active.value = false
    if (typeof document === 'undefined') return
    document.body.style.overflow = ''
    document.removeEventListener('keydown', options.onEscape)
    document.removeEventListener('click', options.onDocumentClick)
  }

  return { active, activate, deactivate, syncModalState }
}
