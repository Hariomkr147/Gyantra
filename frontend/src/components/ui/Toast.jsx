import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

const ToastContext = createContext(null)

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
}

// Toasts render over both themes, so they use semantic tokens. The previous
// emerald-950/red-950 backgrounds were invisible on the light workspace.
const TONES = {
  success: 'border-[rgb(var(--success-fg)/0.4)] bg-surface',
  error: 'border-[rgb(var(--danger-fg)/0.4)] bg-surface',
  warning: 'border-[rgb(var(--warn-fg)/0.4)] bg-surface',
  info: 'border-strong bg-surface',
}

const ICON_TONES = {
  success: 'text-success',
  error: 'text-danger',
  warning: 'text-warn',
  info: 'text-accent-fg',
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback(
    (message, { type = 'info', duration = 4500, title } = {}) => {
      const id = Math.random().toString(36).slice(2)
      setToasts((list) => [...list, { id, message, type, title }])
      if (duration > 0) setTimeout(() => dismiss(id), duration)
      return id
    },
    [dismiss],
  )

  const value = useMemo(
    () => ({
      toast,
      dismiss,
      success: (m, o) => toast(m, { ...o, type: 'success' }),
      error: (m, o) => toast(m, { ...o, type: 'error', duration: 7000 }),
      warning: (m, o) => toast(m, { ...o, type: 'warning' }),
      info: (m, o) => toast(m, { ...o, type: 'info' }),
    }),
    [toast, dismiss],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}

      {/* Screen readers announce toasts without stealing focus. */}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2 px-4 sm:px-0"
      >
        <AnimatePresence initial={false}>
          {toasts.map((t) => {
            const Icon = ICONS[t.type] || Info
            return (
              <motion.div
                key={t.id}
                layout
                initial={{ opacity: 0, y: 12, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, x: 16, scale: 0.97 }}
                transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
                className={cn(
                  'pointer-events-auto flex items-start gap-3 rounded-xl border',
                  'px-4 py-3 shadow-lg shadow-black/10',
                  TONES[t.type],
                )}
              >
                <Icon
                  size={17}
                  className={cn('mt-0.5 shrink-0', ICON_TONES[t.type])}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  {t.title && (
                    <p className="text-[13px] font-semibold text-fg-strong">
                      {t.title}
                    </p>
                  )}
                  <p className="text-[13px] leading-relaxed text-fg-muted">
                    {t.message}
                  </p>
                </div>
                <button
                  onClick={() => dismiss(t.id)}
                  aria-label="Dismiss notification"
                  className="shrink-0 rounded p-0.5 text-fg-subtle transition-colors hover:text-fg"
                >
                  <X size={14} />
                </button>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
