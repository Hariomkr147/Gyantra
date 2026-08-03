import { useState, useId } from 'react'
import { ChevronDown } from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { cn } from '@/lib/utils'

/**
 * Accessible collapsible section.
 * Motion is a short height/opacity transition — no bounce, per the spec.
 */
export function Disclosure({
  title,
  subtitle,
  badge,
  defaultOpen = false,
  children,
  className,
  headerClassName,
}) {
  const [open, setOpen] = useState(defaultOpen)
  const panelId = useId()

  return (
    <div className={cn('surface overflow-hidden', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        className={cn(
          'flex w-full items-center gap-3 px-5 py-4 text-left',
          'transition-colors hover:bg-app-subtle',
          headerClassName,
        )}
      >
        <ChevronDown
          size={16}
          className={cn(
            'shrink-0 text-fg-subtle transition-transform duration-200',
            open && 'rotate-180',
          )}
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-semibold text-fg-strong">
            {title}
          </span>
          {subtitle && (
            <span className="mt-0.5 block truncate text-[13px] text-fg-muted">
              {subtitle}
            </span>
          )}
        </span>
        {badge}
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={panelId}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="border-t border-default px-5 py-4">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** Horizontal tab bar with arrow-key navigation. */
export function Tabs({ tabs, active, onChange, className }) {
  const onKeyDown = (e) => {
    const i = tabs.findIndex((t) => t.id === active)
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      onChange(tabs[(i + 1) % tabs.length].id)
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      onChange(tabs[(i - 1 + tabs.length) % tabs.length].id)
    }
  }

  return (
    <div
      role="tablist"
      onKeyDown={onKeyDown}
      className={cn(
        'flex gap-1 overflow-x-auto border-b border-default pb-px',
        className,
      )}
    >
      {tabs.map((tab) => {
        const selected = tab.id === active
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            className={cn(
              'relative whitespace-nowrap rounded-t-lg px-3.5 py-2.5',
              'text-[13.5px] font-medium transition-colors',
              selected ? 'text-accent-fg' : 'text-fg-muted hover:text-fg',
            )}
          >
            <span className="flex items-center gap-2">
              {tab.label}
              {tab.count !== undefined && tab.count !== null && (
                <span
                  className={cn(
                    'rounded-full px-1.5 py-0.5 text-[10.5px] font-semibold tabular-nums',
                    selected
                      ? 'bg-accent-soft text-accent-fg'
                      : 'bg-app-subtle text-fg-subtle',
                  )}
                >
                  {tab.count}
                </span>
              )}
            </span>
            {selected && (
              <motion.span
                layoutId="tab-underline"
                className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-[rgb(var(--accent))]"
                transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
              />
            )}
          </button>
        )
      })}
    </div>
  )
}
