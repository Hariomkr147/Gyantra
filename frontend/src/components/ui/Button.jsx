import { forwardRef } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

/*
  Variants use semantic tokens so a button looks correct on the dark landing
  page and the light workspace without either page overriding it.
*/
const VARIANTS = {
  primary:
    'bg-accent-solid text-white hover:brightness-110 active:brightness-95 shadow-sm',
  secondary:
    'border border-strong bg-surface text-fg hover:bg-app-subtle',
  ghost: 'text-fg-muted hover:bg-app-subtle hover:text-fg',
  danger:
    'border border-[rgb(var(--danger-fg)/0.35)] bg-[rgb(var(--danger-fg)/0.1)] text-danger hover:bg-[rgb(var(--danger-fg)/0.18)]',
}

const SIZES = {
  sm: 'h-8 px-3 text-[13px] gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-12 px-6 text-[15px] gap-2',
}

export const Button = forwardRef(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    disabled,
    className,
    children,
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-lg font-medium',
        'transition-all duration-150',
        'disabled:cursor-not-allowed disabled:opacity-50',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {loading && <Loader2 size={15} className="animate-spin" aria-hidden="true" />}
      {children}
    </button>
  )
})

export function IconButton({ label, className, children, ...props }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cn(
        'inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
        'text-fg-subtle transition-colors hover:bg-app-subtle hover:text-fg',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}
