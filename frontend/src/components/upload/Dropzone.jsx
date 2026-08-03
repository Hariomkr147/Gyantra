import { useCallback, useRef, useState } from 'react'
import { FileText, Upload, X } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn, formatBytes } from '@/lib/utils'
import { IconButton } from '@/components/ui/Button'

const DEFAULT_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md']

/**
 * File dropzone with keyboard and click fallbacks.
 * Validates extension and size client-side so the user gets instant feedback,
 * but the backend re-validates — this is convenience, not a security boundary.
 */
export function Dropzone({
  file,
  onFile,
  onClear,
  extensions = DEFAULT_EXTENSIONS,
  maxSizeMb = 25,
  disabled = false,
}) {
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef(null)

  const validate = useCallback(
    (candidate) => {
      const name = candidate.name.toLowerCase()
      const ok = extensions.some((ext) => name.endsWith(ext))
      if (!ok) {
        return `Unsupported file type. Accepted: ${extensions.join(', ')}`
      }
      if (candidate.size === 0) return 'That file is empty.'
      if (candidate.size > maxSizeMb * 1024 * 1024) {
        return `File is ${formatBytes(candidate.size)}, over the ${maxSizeMb} MB limit.`
      }
      return ''
    },
    [extensions, maxSizeMb],
  )

  const accept = useCallback(
    (candidate) => {
      if (!candidate) return
      const problem = validate(candidate)
      if (problem) {
        setError(problem)
        return
      }
      setError('')
      onFile(candidate)
    },
    [onFile, validate],
  )

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    if (disabled) return
    accept(e.dataTransfer.files?.[0])
  }

  if (file) {
    return (
      <div>
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
          className="flex items-center gap-3.5 rounded-xl border border-accent-soft bg-accent-soft] px-4 py-3.5"
        >
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-fg">
            <FileText size={19} aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-fg-strong" title={file.name}>
              {file.name}
            </p>
            <p className="mt-0.5 text-xs text-fg-subtle">{formatBytes(file.size)}</p>
          </div>
          {!disabled && (
            <IconButton label="Remove file" onClick={onClear}>
              <X size={16} />
            </IconButton>
          )}
        </motion.div>
        {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      </div>
    )
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (disabled) return
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'group relative flex cursor-pointer flex-col items-center justify-center',
          'rounded-xl border-2 border-dashed px-6 py-12 text-center',
          'transition-colors duration-200',
          dragging
            ? 'border-[rgb(var(--accent))] bg-accent-soft]'
            : 'border-strong hover:border-strong hover:bg-surface',
          disabled && 'cursor-not-allowed opacity-50',
        )}
      >
        <div
          className={cn(
            'mb-4 flex h-12 w-12 items-center justify-center rounded-xl transition-colors',
            dragging
              ? 'bg-accent-soft text-accent-fg'
              : 'bg-app-subtle text-fg-muted group-hover:text-fg-muted',
          )}
        >
          <Upload size={21} aria-hidden="true" />
        </div>

        <p className="text-[15px] font-medium text-fg-strong">
          {dragging ? 'Drop to upload' : 'Drop a chapter here'}
        </p>
        <p className="mt-1.5 text-[13px] text-fg-subtle">
          or <span className="text-accent-fg">browse your files</span>
        </p>
        <p className="mt-3.5 text-[11.5px] text-fg-subtle">
          {extensions.join(' · ')} — up to {maxSizeMb} MB
        </p>

        <input
          ref={inputRef}
          type="file"
          accept={extensions.join(',')}
          onChange={(e) => {
            accept(e.target.files?.[0])
            e.target.value = ''
          }}
          className="sr-only"
          tabIndex={-1}
        />
      </div>
      {error && (
        <p role="alert" className="mt-2 text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  )
}
