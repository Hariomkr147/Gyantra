import { cn } from '@/lib/utils'

/*
  Status chips. Colour is always paired with text, never the sole signal —
  an accessibility requirement from the spec.
*/

const TONES = {
  neutral: 'bg-app-subtle text-fg-muted border-default',
  accent: 'bg-accent-soft text-accent-fg border-accent-soft',
  success:
    'bg-[rgb(var(--success-fg)/0.13)] text-success border-[rgb(var(--success-fg)/0.28)]',
  warn: 'bg-[rgb(var(--warn-fg)/0.13)] text-warn border-[rgb(var(--warn-fg)/0.28)]',
  danger:
    'bg-[rgb(var(--danger-fg)/0.13)] text-danger border-[rgb(var(--danger-fg)/0.28)]',
}

export function Badge({ children, tone = 'neutral', className, icon: Icon }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border',
        'px-2.5 py-0.5 text-[11.5px] font-medium leading-5',
        TONES[tone] || TONES.neutral,
        className,
      )}
    >
      {Icon && <Icon size={12} aria-hidden="true" />}
      {children}
    </span>
  )
}

const VALIDATION_TONE = { pass: 'success', warn: 'warn', fail: 'danger' }
const VALIDATION_LABEL = { pass: 'Passed', warn: 'Warnings', fail: 'Failed' }

export function ValidationPill({ status, className }) {
  return (
    <Badge tone={VALIDATION_TONE[status] || 'warn'} className={className}>
      {VALIDATION_LABEL[status] || status}
    </Badge>
  )
}

const SEVERITY_TONE = { high: 'danger', medium: 'warn', low: 'accent' }

export function SeverityPill({ severity, className }) {
  return (
    <Badge
      tone={SEVERITY_TONE[severity] || 'warn'}
      className={cn('uppercase tracking-wide', className)}
    >
      {severity}
    </Badge>
  )
}

const STATUS_TONE = {
  completed: 'success',
  running: 'accent',
  queued: 'neutral',
  failed: 'danger',
  cancelled: 'neutral',
}

/** Job status chip, used in the dashboard and library lists. */
export function StatusBadge({ status, className }) {
  return (
    <Badge tone={STATUS_TONE[status] || 'neutral'} className={cn('capitalize', className)}>
      {status === 'running' ? 'In progress' : status}
    </Badge>
  )
}

/**
 * Marks whether content came from the source document or was added as teaching
 * scaffolding. This distinction is a core product guarantee, so it gets its own
 * component rather than an ad-hoc label.
 */
export function GroundingBadge({ origin = 'source', className }) {
  const isSource = origin === 'source'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5',
        'text-[11px] font-medium leading-5',
        isSource
          ? 'border-accent-soft bg-accent-soft text-accent-fg'
          : 'border-default bg-app-subtle text-fg-subtle',
        className,
      )}
      title={
        isSource
          ? 'Derived from the uploaded document'
          : 'Teaching support added by the model, not source subject matter'
      }
    >
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full',
          isSource ? 'bg-[rgb(var(--accent))]' : 'bg-[rgb(var(--fg-subtle))]',
        )}
        aria-hidden="true"
      />
      {isSource ? 'From source' : 'Pedagogical support'}
    </span>
  )
}
