import { cn } from '@/lib/utils'

export function Card({ className, children, hover = false, ...props }) {
  return (
    <div
      className={cn('surface', hover && 'surface-hover', className)}
      {...props}
    >
      {children}
    </div>
  )
}

export function CardHeader({ className, children }) {
  return (
    <div className={cn('border-b border-default px-5 py-4', className)}>
      {children}
    </div>
  )
}

export function CardBody({ className, children }) {
  return <div className={cn('px-5 py-4', className)}>{children}</div>
}

export function CardTitle({ className, children, as: Tag = 'h3' }) {
  return (
    <Tag className={cn('text-[15px] font-semibold text-fg-strong', className)}>
      {children}
    </Tag>
  )
}

/** Section heading used above a group of cards. */
export function SectionLabel({ children, className, action }) {
  return (
    <div className={cn('mb-3 flex items-center justify-between gap-3', className)}>
      <h2 className="eyebrow">{children}</h2>
      {action}
    </div>
  )
}

/** Label/value pair used across overview and metadata panels. */
export function Stat({ label, value, hint, className }) {
  const empty = value === null || value === undefined || value === ''
  return (
    <div className={cn('min-w-0', className)}>
      <dt className="eyebrow">{label}</dt>
      <dd
        className="mt-1 truncate text-[15px] font-semibold text-fg-strong"
        title={empty ? undefined : String(value)}
      >
        {empty ? <span className="text-fg-subtle">—</span> : value}
      </dd>
      {hint && <p className="mt-0.5 text-xs text-fg-subtle">{hint}</p>}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, description, action, className }) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-xl border border-dashed',
        'border-strong bg-surface-sunken px-6 py-16 text-center',
        className,
      )}
    >
      {Icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-accent-soft text-accent-fg">
          <Icon size={22} aria-hidden="true" />
        </div>
      )}
      <h3 className="text-[16px] font-semibold text-fg-strong">{title}</h3>
      {description && (
        <p className="mt-2 max-w-sm text-[13.5px] leading-relaxed text-fg-muted">
          {description}
        </p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}

export function Skeleton({ className }) {
  return <div className={cn('skeleton h-4 w-full', className)} />
}

/** Loading placeholder shaped like a list of rows. */
export function SkeletonList({ rows = 4, className }) {
  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="surface flex items-center gap-4 px-4 py-3.5"
        >
          <div className="skeleton h-10 w-10 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="skeleton h-3.5 w-1/3" />
            <div className="skeleton h-3 w-1/4" />
          </div>
          <div className="skeleton h-5 w-20 shrink-0 rounded-full" />
        </div>
      ))}
    </div>
  )
}

/** Loading placeholder shaped like a content panel. */
export function SkeletonPanel({ className }) {
  return (
    <div className={cn('surface space-y-4 p-5', className)}>
      <div className="skeleton h-4 w-40" />
      <div className="space-y-2">
        <div className="skeleton h-3 w-full" />
        <div className="skeleton h-3 w-11/12" />
        <div className="skeleton h-3 w-4/5" />
      </div>
    </div>
  )
}
