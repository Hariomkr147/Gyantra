import { motion } from 'framer-motion'
import { AlertCircle, Check, Loader2, SkipForward } from 'lucide-react'
import { cn, formatDuration } from '@/lib/utils'
import { STAGE_META } from '@/lib/constants'

function StageIcon({ status }) {
  if (status === 'completed')
    return <Check size={13} strokeWidth={3} aria-hidden="true" />
  if (status === 'running')
    return <Loader2 size={13} className="animate-spin" aria-hidden="true" />
  if (status === 'failed')
    return <AlertCircle size={13} aria-hidden="true" />
  if (status === 'skipped')
    return <SkipForward size={12} aria-hidden="true" />
  return null
}

const DOT_STYLES = {
  completed: 'border-[rgb(var(--accent))] bg-[rgb(var(--accent))] text-white',
  running: 'border-[rgb(var(--accent))] bg-accent-soft text-accent-fg',
  failed: 'border-[rgb(var(--danger-fg))] bg-[rgb(var(--danger-fg)/0.1)] text-danger',
  skipped: 'border-strong bg-app-subtle text-fg-subtle',
  pending: 'border-strong bg-surface text-fg-subtle',
}

/**
 * Vertical stage list with a connecting rail.
 * Shows all ten stages up front so the teacher can see the whole process,
 * with live status, duration and notes as each one resolves.
 */
export function PipelineStepper({ stages = [], className }) {
  if (!stages.length) {
    return (
      <div className={cn('space-y-3', className)}>
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="skeleton h-6 w-6 rounded-full" />
            <div className="skeleton h-3.5 w-40" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <ol className={cn('relative space-y-0.5', className)}>
      {stages.map((stage, i) => {
        const meta = STAGE_META[stage.stage] || {}
        const status = stage.status || 'pending'
        const isLast = i === stages.length - 1
        const active = status === 'running'

        return (
          <li key={stage.stage} className="relative flex gap-3.5 pb-3.5">
            {/* Connector rail */}
            {!isLast && (
              <span
                className={cn(
                  'absolute left-[11px] top-7 h-[calc(100%-1rem)] w-px',
                  status === 'completed' ? 'bg-accent-solid/45' : 'bg-app-subtle',
                )}
                aria-hidden="true"
              />
            )}

            <span
              className={cn(
                'relative z-10 mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center',
                'rounded-full border transition-colors duration-300',
                DOT_STYLES[status],
              )}
            >
              <StageIcon status={status} />
              {active && (
                <motion.span
                  className="absolute inset-0 rounded-full border border-[rgb(var(--accent))]"
                  animate={{ scale: [1, 1.5], opacity: [0.6, 0] }}
                  transition={{ duration: 1.6, repeat: Infinity, ease: 'easeOut' }}
                  aria-hidden="true"
                />
              )}
            </span>

            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex items-baseline justify-between gap-3">
                <p
                  className={cn(
                    'text-[13.5px] font-medium transition-colors',
                    status === 'completed' && 'text-fg',
                    active && 'text-accent-fg',
                    status === 'failed' && 'text-danger',
                    (status === 'pending' || status === 'skipped') && 'text-fg-subtle',
                  )}
                >
                  {meta.label || stage.stage}
                </p>
                {stage.duration_seconds > 0 && (
                  <span className="shrink-0 font-mono text-[11px] tabular-nums text-fg-subtle">
                    {formatDuration(stage.duration_seconds)}
                  </span>
                )}
              </div>

              {/* Live detail while running, notes once resolved. */}
              {active && stage.message ? (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="mt-0.5 text-[12px] leading-snug text-accent-fg/80"
                >
                  {stage.message}
                </motion.p>
              ) : status === 'pending' && meta.blurb ? (
                <p className="mt-0.5 text-[12px] leading-snug text-fg-subtle">
                  {meta.blurb}
                </p>
              ) : stage.message ? (
                <p
                  className={cn(
                    'mt-0.5 text-[12px] leading-snug',
                    status === 'failed' ? 'text-danger/90' : 'text-fg-subtle',
                  )}
                >
                  {stage.message}
                </p>
              ) : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** Determinate progress bar with a subtle sheen while active. */
export function ProgressBar({ value = 0, active = false, className }) {
  const clamped = Math.max(0, Math.min(100, value))

  return (
    <div
      className={cn('h-1.5 w-full overflow-hidden rounded-full bg-app-subtle', className)}
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Pipeline progress"
    >
      <motion.div
        className={cn(
          'relative h-full rounded-full bg-[rgb(var(--accent))]',
          active &&
            'bg-gradient-to-r from-[rgb(var(--accent))] via-[rgb(var(--accent-fg))] to-[rgb(var(--accent))]',
        )}
        style={active ? { backgroundSize: '200% 100%' } : undefined}
        initial={false}
        animate={{ width: `${clamped}%` }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        {active && (
          <span
            className="absolute inset-0 animate-shimmer rounded-full"
            style={{
              backgroundImage:
                'linear-gradient(90deg, transparent, rgba(255,255,255,0.35), transparent)',
              backgroundSize: '200% 100%',
            }}
            aria-hidden="true"
          />
        )}
      </motion.div>
    </div>
  )
}
