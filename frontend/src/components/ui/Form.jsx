import { useId } from 'react'
import { cn } from '@/lib/utils'

export function Field({ label, hint, error, children, className, required, htmlFor }) {
  const generatedId = useId()
  const id = htmlFor || generatedId

  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={id} className="block text-[13px] font-medium text-fg">
        {label}
        {required && (
          <span className="ml-0.5 text-accent-fg" aria-hidden="true">
            *
          </span>
        )}
      </label>
      {typeof children === 'function' ? children(id) : children}
      {error ? (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-fg-subtle">{hint}</p>
      ) : null}
    </div>
  )
}

const CONTROL = cn(
  'w-full rounded-lg border border-strong bg-surface px-3 py-2',
  'text-sm text-fg placeholder:text-fg-subtle',
  'transition-colors focus:border-[rgb(var(--accent))] focus:outline-none',
  'focus:ring-1 focus:ring-[rgb(var(--accent))] disabled:opacity-50',
)

export function TextInput({ className, ...props }) {
  return <input className={cn(CONTROL, className)} {...props} />
}

export function Select({ className, options = [], ...props }) {
  return (
    <select className={cn(CONTROL, 'cursor-pointer', className)} {...props}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export function Textarea({ className, ...props }) {
  return <textarea className={cn(CONTROL, 'resize-y', className)} {...props} />
}

/**
 * Radio group rendered as selectable cards.
 * Used for the document-type hint, which drives cost-aware parser routing.
 */
export function OptionCards({ name, value, onChange, options, columns = 2 }) {
  return (
    <div
      role="radiogroup"
      className={cn(
        'grid gap-2',
        columns === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2',
      )}
    >
      {options.map((opt) => {
        const selected = value === opt.value
        return (
          <label
            key={opt.value}
            className={cn(
              'group relative cursor-pointer rounded-lg border p-3',
              'transition-all duration-150',
              selected
                ? 'border-[rgb(var(--accent))] bg-accent-soft'
                : 'border-default bg-surface hover:border-strong hover:bg-app-subtle',
            )}
          >
            <input
              type="radio"
              name={name}
              value={opt.value}
              checked={selected}
              onChange={() => onChange(opt.value)}
              className="sr-only"
            />
            <div className="flex items-start gap-2.5">
              <span
                className={cn(
                  'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border',
                  selected ? 'border-[rgb(var(--accent))]' : 'border-strong',
                )}
                aria-hidden="true"
              >
                {selected && (
                  <span className="h-2 w-2 rounded-full bg-[rgb(var(--accent))]" />
                )}
              </span>
              <span className="min-w-0">
                <span
                  className={cn(
                    'block text-[13px] font-medium',
                    selected ? 'text-accent-fg' : 'text-fg',
                  )}
                >
                  {opt.label}
                </span>
                {opt.hint && (
                  <span className="mt-0.5 block text-[11.5px] leading-snug text-fg-subtle">
                    {opt.hint}
                  </span>
                )}
              </span>
            </div>
          </label>
        )
      })}
    </div>
  )
}
