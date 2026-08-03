import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  FileText,
  History,
  Loader2,
  Sparkles,
  Upload,
} from 'lucide-react'
import {
  Card,
  CardBody,
  EmptyState,
  SectionLabel,
  SkeletonList,
} from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { StatusBadge } from '@/components/ui/Badge'
import { listJobs } from '@/lib/api'
import { cn, formatBytes, formatRelativeTime } from '@/lib/utils'

function JobRow({ job }) {
  const to =
    job.status === 'completed'
      ? `/app/output/${job.job_id}`
      : `/app/job/${job.job_id}`

  const StatusIcon =
    job.status === 'completed'
      ? CheckCircle2
      : job.status === 'failed'
        ? AlertCircle
        : Loader2

  return (
    <Link
      to={to}
      className={cn(
        'surface surface-hover group flex items-center gap-4 px-4 py-3.5',
        'focus-visible:ring-2 focus-visible:ring-[rgb(var(--accent))]',
      )}
    >
      <span
        className={cn(
          'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
          job.status === 'failed'
            ? 'bg-[rgb(var(--danger-fg)/0.12)] text-danger'
            : 'bg-accent-soft text-accent-fg',
        )}
      >
        <FileText size={18} aria-hidden="true" />
      </span>

      <span className="min-w-0 flex-1">
        <span
          className="block truncate text-[14px] font-medium text-fg-strong"
          title={job.file_name}
        >
          {job.file_name}
        </span>
        <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-fg-subtle">
          {job.file_size_bytes > 0 && <span>{formatBytes(job.file_size_bytes)}</span>}
          {job.file_size_bytes > 0 && <span aria-hidden="true">·</span>}
          <span>{formatRelativeTime(job.created_at)}</span>
          {job.status === 'running' && job.progress > 0 && (
            <>
              <span aria-hidden="true">·</span>
              <span className="text-accent-fg">{job.progress}% complete</span>
            </>
          )}
        </span>
      </span>

      <StatusBadge status={job.status} className="hidden sm:inline-flex" />
      <StatusIcon
        size={16}
        className={cn(
          'shrink-0 sm:hidden',
          job.status === 'completed' && 'text-success',
          job.status === 'failed' && 'text-danger',
          job.status === 'running' && 'animate-spin text-accent-fg',
          job.status === 'queued' && 'text-fg-subtle',
        )}
        aria-hidden="true"
      />

      <ArrowRight
        size={15}
        className="hidden shrink-0 text-fg-subtle transition-transform group-hover:translate-x-0.5 sm:block"
        aria-hidden="true"
      />
    </Link>
  )
}

function QuickAction({ to, icon: Icon, title, description }) {
  return (
    <Link to={to} className="block">
      <Card hover className="flex h-full items-center gap-4 p-4">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent-fg">
          <Icon size={19} aria-hidden="true" />
        </span>
        <span className="min-w-0">
          <span className="block text-[14px] font-semibold text-fg-strong">
            {title}
          </span>
          <span className="mt-0.5 block text-[12.5px] text-fg-muted">
            {description}
          </span>
        </span>
      </Card>
    </Link>
  )
}

export default function Dashboard() {
  const [jobs, setJobs] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    listJobs(20)
      .then((data) => !cancelled && setJobs(data.jobs || []))
      .catch(() => !cancelled && setJobs([]))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  const recent = (jobs || []).slice(0, 6)
  const completed = (jobs || []).filter((j) => j.status === 'completed').length

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-8">
        <h1 className="font-display text-[28px] font-semibold tracking-tight text-fg-strong">
          Dashboard
        </h1>
        <p className="mt-1.5 text-[14.5px] text-fg-muted">
          Upload a chapter and Gyantra builds the teaching package around it.
        </p>
      </header>

      <div className="mb-8 grid gap-3 sm:grid-cols-2">
        <QuickAction
          to="/app/upload"
          icon={Upload}
          title="New package"
          description="Upload a chapter to get started"
        />
        <QuickAction
          to="/app/library"
          icon={History}
          title="Library"
          description={
            completed > 0
              ? `${completed} package${completed === 1 ? '' : 's'} ready to review`
              : 'Everything you have generated'
          }
        />
      </div>

      {loading ? (
        <>
          <SectionLabel>Recent</SectionLabel>
          <SkeletonList rows={4} />
        </>
      ) : recent.length === 0 ? (
        <EmptyState
          icon={Sparkles}
          title="No packages yet"
          description="Upload a textbook chapter, lecture notes, or any educational document. Gyantra extracts the concepts and builds a lesson plan, activities and assessments around them."
          action={
            <Link to="/app/upload">
              <Button size="lg">
                <Upload size={16} />
                Upload a chapter
              </Button>
            </Link>
          }
        />
      ) : (
        <>
          <SectionLabel
            action={
              <Link
                to="/app/library"
                className="text-[13px] font-medium text-accent-fg transition-opacity hover:opacity-80"
              >
                View all
              </Link>
            }
          >
            Recent
          </SectionLabel>
          <div className="space-y-2">
            {recent.map((job) => (
              <JobRow key={job.job_id} job={job} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
