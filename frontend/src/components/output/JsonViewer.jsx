import { useMemo, useState } from 'react'
import { Check, ChevronRight, Copy, Download, Search } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Form'
import { cn, copyToClipboard, downloadJson } from '@/lib/utils'

/** Collapsible JSON tree. Renders lazily — only expanded nodes mount. */
function Node({ name, value, depth = 0, defaultOpen = false, filter = '' }) {
  const [open, setOpen] = useState(defaultOpen || depth < 1)

  const type = Array.isArray(value) ? 'array' : value === null ? 'null' : typeof value
  const isBranch = type === 'object' || type === 'array'

  // Hide subtrees that don't match an active search.
  const matches = useMemo(() => {
    if (!filter) return true
    const needle = filter.toLowerCase()
    if (String(name).toLowerCase().includes(needle)) return true
    try {
      return JSON.stringify(value).toLowerCase().includes(needle)
    } catch {
      return false
    }
  }, [filter, name, value])

  if (!matches) return null

  if (!isBranch) {
    const display =
      type === 'string'
        ? `"${value}"`
        : value === null
          ? 'null'
          : String(value)

    return (
      <div
        className="flex gap-2 py-[3px] font-mono text-[12.5px] leading-relaxed"
        style={{ paddingLeft: `${depth * 14}px` }}
      >
        <span className="shrink-0 text-syn-key">{name}:</span>
        <span
          className={cn(
            'min-w-0 break-all',
            type === 'string' && 'text-syn-string',
            type === 'number' && 'text-syn-number',
            type === 'boolean' && 'text-syn-boolean',
            type === 'null' && 'text-fg-subtle',
          )}
        >
          {display}
        </span>
      </div>
    )
  }

  const entries = type === 'array'
    ? value.map((v, i) => [String(i), v])
    : Object.entries(value)

  const summary = type === 'array' ? `[${entries.length}]` : `{${entries.length}}`

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-1 rounded py-[3px] text-left font-mono text-[12.5px] hover:bg-app-subtle"
        style={{ paddingLeft: `${depth * 14}px` }}
      >
        <ChevronRight
          size={12}
          className={cn(
            'shrink-0 text-fg-subtle transition-transform',
            open && 'rotate-90',
          )}
          aria-hidden="true"
        />
        <span className="text-syn-key">{name}</span>
        <span className="text-fg-subtle">{summary}</span>
      </button>

      {open &&
        entries.map(([k, v]) => (
          <Node key={k} name={k} value={v} depth={depth + 1} filter={filter} />
        ))}
    </div>
  )
}

/**
 * JSON preview with search, copy and download.
 * Tree view for exploring; raw view for copying into other tools.
 */
export function JsonViewer({ data, filename = 'TeacherKnowledgePackage.json' }) {
  const [mode, setMode] = useState('tree')
  const [filter, setFilter] = useState('')
  const [copied, setCopied] = useState(false)

  const raw = useMemo(() => JSON.stringify(data, null, 2), [data])

  const onCopy = async () => {
    const ok = await copyToClipboard(raw)
    if (ok) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    }
  }

  const sizeKb = (new Blob([raw]).size / 1024).toFixed(1)

  return (
    <div className="surface overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-default px-4 py-3">
        <div className="flex rounded-lg border border-strong p-0.5">
          {['tree', 'raw'].map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={cn(
                'rounded-md px-2.5 py-1 text-[12px] font-medium capitalize transition-colors',
                mode === m
                  ? 'bg-accent-soft text-accent-fg'
                  : 'text-fg-subtle hover:text-fg-muted',
              )}
            >
              {m}
            </button>
          ))}
        </div>

        {mode === 'tree' && (
          <div className="relative min-w-[160px] flex-1">
            <Search
              size={13}
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-subtle"
              aria-hidden="true"
            />
            <TextInput
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search keys and values"
              aria-label="Search JSON"
              className="h-8 py-1 pl-8 text-[12.5px]"
            />
          </div>
        )}

        <div className="ml-auto flex items-center gap-1.5">
          <span className="hidden font-mono text-[11px] text-fg-subtle sm:inline">
            {sizeKb} KB
          </span>
          <Button variant="ghost" size="sm" onClick={onCopy}>
            {copied ? <Check size={13} /> : <Copy size={13} />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => downloadJson(data, filename)}
          >
            <Download size={13} />
            Download
          </Button>
        </div>
      </div>

      <div className="max-h-[62vh] overflow-auto bg-surface-sunken p-4">
        {mode === 'tree' ? (
          <div>
            {Object.entries(data || {}).map(([k, v]) => (
              <Node key={k} name={k} value={v} filter={filter} />
            ))}
          </div>
        ) : (
          <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-fg-muted">
            {raw}
          </pre>
        )}
      </div>
    </div>
  )
}
