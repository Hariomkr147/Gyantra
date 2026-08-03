import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, FileText, Search, Trash2, Upload } from 'lucide-react'
import { EmptyState, SkeletonList } from '@/components/ui/Card'
import { Button, IconButton } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/Form'
import { StatusBadge } from '@/components/ui/Badge'
import { useToast } from '@/components/ui/Toast'
import { deleteJob, listJobs } from '@/lib/api'
import { cn, formatBytes, formatRelativeTime } from '@/lib/utils'

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'completed', label: 'Completed' },
  { id: 'running', label: 'In progress' },
  { id: 'failed', label: 'Failed' },
]

export default function Library() {
  const toast = useToast()
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [deleting, setDeleting] = useState(null)

  useEffect(() => {
    let cancelled = false
    listJobs(100)
      .then((data) => !cancelled && setJobs(data.jobs || []))
      .catch((err) => !cancelled && toast.error(err.message))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const counts = useMemo(() => {
    const c = { all: jobs.length, completed: 0, running: 0, failed: 0 }
    for (const j of jobs) {
      if (j.status === 'completed') c.completed += 1
      else if (j.status === 'failed') c.failed += 1
      else c.running += 1
    }
    return c
  }, [jobs])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return jobs.filter((job) => {
      if (filter === 'running') {
        if (!['running', 'queued'].includes(job.status)) return false
      } else if (filter !== 'all' && job.status !== filter) {
        return false
      }
      if (needle && !job.file_name.toLowerCase().includes(needle)) return false
      return true
    })
  }, [jobs, query, filter])

  const onDelete = async (job) => {
    const ok = window.confirm(
      `Delete the package for "${job.file_name}"?\n\n` +
        'This removes the job and its exported files, and cannot be undone.',
    )
    if (!ok) return

    setDeleting(job.job_id)
    try {
      await deleteJob(job.job_id)
      setJobs((list) => list.filter((j) => j.job_id !== job.job_id))
      toast.success('Package deleted')
    } catch (err) {
      toast.error(err.message)
    } finally {
      setDeleting(null)
    }
  }

  const filtering = Boolean(query) || filter !== 'all'

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-[28px] font-semibold tracking-tight text-fg-strong">
            Library
          </h1>
          <p className="mt-1.5 text-[14.5px] text-fg-muted">
            {jobs.length > 0
              ? `${jobs.length} package${jobs.length === 1 ? '' : 's'} generated`
              : 'Every package you have generated.'}
          </p>
        </div>
        <Link to="/app/upload">
          <Button>
            <Upload size={15} />
            New package
          </Button>
        </Link>
      </header>

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-subtle"
            aria-hidden="true"
          />
          <TextInput
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by filename"
            aria-label="Search packages"
            className="pl-9"
          />
        </div>

        <div
          role="tablist"
          aria-label="Filter by status"
          className="flex overflow-x-auto rounded-lg border border-default bg-surface p-0.5"
        >
          {FILTERS.map((f) => (
            <button
              key={f.id}
              role="tab"
              aria-selected={filter === f.id}
              onClick={() => setFilter(f.id)}
              className={cn(
                'whitespace-nowrap rounded-md px-3 py-1.5 text-[12.5px] font-medium transition-colors',
                filter === f.id
                  ? 'bg-accent-soft text-accent-fg'
                  : 'text-fg-muted hover:text-fg',
              )}
            >
              {f.label}
              {counts[f.id] > 0 && (
                <span className="ml-1.5 tabular-nums opacity-70">
                  {counts[f.id]}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <SkeletonList rows={5} />
      ) : visible.length === 0 ? (
        <EmptyState
          icon={filtering ? Search : Upload}
          title={filtering ? 'Nothing matches that filter' : 'No packages yet'}
          description={
            filtering
              ? 'Try a different search term or status filter.'
              : 'Upload a chapter to generate your first teaching package.'
          }
          action={
            filtering ? (
              <Button
                variant="secondary"
                onClick={() => {
                  setQuery('')
                  setFilter('all')
                }}
              >
                Clear filters
              </Button>
            ) : (
              <Link to="/app/upload">
                <Button size="lg">
                  <Upload size={16} />
                  Upload a chapter
                </Button>
              </Link>
            )
          }
        />
      ) : (
        <ul className="space-y-2">
          {visible.map((job) => (
            <li
              key={job.job_id}
              className="surface surface-hover flex items-center gap-3 px-4 py-3.5 sm:gap-4"
            >
              <Link
                to={
                  job.status === 'completed'
                    ? `/app/output/${job.job_id}`
                    : `/app/job/${job.job_id}`
                }
                className="flex min-w-0 flex-1 items-center gap-3 sm:gap-4"
              >
                <span
                  className={cn(
                    'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
                    job.status === 'failed'
                      ? 'bg-[rgb(var(--danger-fg)/0.12)] text-danger'
                      : 'bg-accent-soft text-accent-fg',
                  )}
                >
                  {job.status === 'failed' ? (
                    <AlertCircle size={18} aria-hidden="true" />
                  ) : (
                    <FileText size={18} aria-hidden="true" />
                  )}
                </span>

                <span className="min-w-0 flex-1">
                  <span
                    className="block truncate text-[14px] font-medium text-fg-strong"
                    title={job.file_name}
                  >
                    {job.file_name}
                  </span>
                  <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[12px] text-fg-subtle">
                    {job.file_size_bytes > 0 && (
                      <>
                        <span>{formatBytes(job.file_size_bytes)}</span>
                        <span aria-hidden="true">·</span>
                      </>
                    )}
                    <span>{formatRelativeTime(job.created_at)}</span>
                    {job.status === 'running' && job.progress > 0 && (
                      <>
                        <span aria-hidden="true">·</span>
                        <span className="text-accent-fg">{job.progress}%</span>
                      </>
                    )}
                  </span>
                  {job.status === 'failed' && job.error_message && (
                    <span
                      className="mt-1 block truncate text-[12px] text-danger"
                      title={job.error_message}
                    >
                      {job.error_message}
                    </span>
                  )}
                </span>

                <StatusBadge
                  status={job.status}
                  className="hidden shrink-0 sm:inline-flex"
                />
              </Link>

              <IconButton
                label={`Delete package for ${job.file_name}`}
                onClick={() => onDelete(job)}
                disabled={deleting === job.job_id}
                className="hover:bg-[rgb(var(--danger-fg)/0.12)] hover:text-danger"
              >
                <Trash2 size={15} />
              </IconButton>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
