import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertCircle,
  BookOpen,
  Braces,
  Boxes,
  Download,
  FileJson,
  FileText,
  Layers,
  ListChecks,
  ScrollText,
  ShieldCheck,
  Target,
} from 'lucide-react'
import { Card, CardBody, EmptyState, Stat } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge, GroundingBadge } from '@/components/ui/Badge'
import { Tabs } from '@/components/ui/Disclosure'
import { PeriodCard } from '@/components/output/PeriodCard'
import { ActivityPanel } from '@/components/output/ActivityPanel'
import { AssessmentPanel } from '@/components/output/AssessmentPanel'
import { GapPanel } from '@/components/output/GapPanel'

import { useToast } from '@/components/ui/Toast'
import { getJob, triggerDownload } from '@/lib/api'
import { DOWNLOAD_FORMATS } from '@/lib/constants'
import { formatDuration, titleCase } from '@/lib/utils'

/* ── overview tab ─────────────────────────────────────────────────────── */

function Overview({ pkg, job }) {
  const profile = pkg.document_profile || {}
  const ke = pkg.knowledge_extraction || {}
  const plan = pkg.teaching_plan || {}
  const meta = pkg.metadata || {}

  // Stages that ran but produced nothing. The backend records this on the job;
  // showing empty tabs without explanation would look like a bug.
  const missing = []
  if (!pkg.activities?.length) missing.push('Activities')
  if (
    !(
      (pkg.assessments?.items?.mcqs?.length || 0) +
      (pkg.assessments?.items?.short_answers?.length || 0) +
      (pkg.assessments?.items?.long_answers?.length || 0) +
      (pkg.assessments?.items?.numericals?.length || 0)
    )
  ) {
    missing.push('Assessments')
  }
  if (!pkg.gap_analysis?.misconceptions?.length) missing.push('Gap analysis')
  if (!pkg.classroom_content?.some((c) => c.teacher_script?.trim())) {
    missing.push('Classroom content')
  }

  return (
    <div className="space-y-5">
      {missing.length > 0 && (
        <Card className="border-l-[3px] border-l-[rgb(var(--warn-fg))]">
          <CardBody className="flex items-start gap-3">
            <AlertCircle
              size={17}
              className="mt-0.5 shrink-0 text-warn"
              aria-hidden="true"
            />
            <div>
              <h3 className="text-[14px] font-semibold text-fg-strong">
                Some sections are empty
              </h3>
              <p className="mt-1 text-[13px] leading-relaxed text-fg-muted">
                {missing.join(', ')} could not be generated.{' '}
                {job?.error_message ||
                  'This usually means the AI provider was rate-limited or unavailable. Re-running the document may fill in the missing sections.'}
              </p>
            </div>
          </CardBody>
        </Card>
      )}

      {meta.demo_mode && (
        <Card className="border-l-2 border-l-[rgb(var(--warn-fg))]">
          <CardBody className="flex items-start gap-3">
            <AlertCircle size={17} className="mt-0.5 shrink-0 text-warn" />
            <div>
              <h3 className="text-[14px] font-semibold text-fg-strong">
                Demo mode output
              </h3>
              <p className="mt-1 text-[13px] leading-relaxed text-fg-subtle">
                This package was produced by the offline stub, not a real model.
                It is structurally valid but pedagogically shallow. Configure an
                API key to generate genuine teaching material.
              </p>
            </div>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardBody>
          <dl className="grid grid-cols-2 gap-5 sm:grid-cols-4">
            <Stat label="Subject" value={profile.subject} />
            <Stat label="Grade" value={profile.grade} />
            <Stat
              label="Difficulty"
              value={profile.difficulty && titleCase(profile.difficulty)}
            />
            <Stat label="Language" value={profile.language?.toUpperCase()} />
          </dl>

          {profile.topic && (
            <div className="mt-5 border-t border-default pt-4">
              <p className="text-[11.5px] font-medium uppercase tracking-wider text-fg-muted">
                Topic
              </p>
              <p className="mt-1 text-[15px] font-medium text-fg-strong">
                {profile.topic}
              </p>
              {profile.chapter && profile.chapter !== profile.topic && (
                <p className="mt-0.5 text-[13px] text-fg-subtle">
                  {profile.chapter}
                </p>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: 'Periods', value: plan.total_periods || 0, icon: Layers },
          { label: 'Concepts', value: ke.concepts?.length || 0, icon: BookOpen },
          { label: 'Activities', value: pkg.activities?.length || 0, icon: Boxes },
          {
            label: 'Misconceptions',
            value: pkg.gap_analysis?.misconceptions?.length || 0,
            icon: Target,
          },
        ].map((s) => (
          <Card key={s.label}>
            <CardBody className="flex items-center gap-3.5">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-fg">
                <s.icon size={18} aria-hidden="true" />
              </div>
              <div>
                <p className="font-display text-2xl font-semibold text-fg-strong">
                  {s.value}
                </p>
                <p className="text-[12px] text-fg-subtle">{s.label}</p>
              </div>
            </CardBody>
          </Card>
        ))}
      </div>

      {plan.adaptation_rationale && (
        <Card>
          <CardBody>
            <h3 className="mb-1.5 text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
              Why this plan structure
            </h3>
            <p className="text-[13.5px] leading-relaxed text-fg-subtle">
              {plan.adaptation_rationale}
            </p>
          </CardBody>
        </Card>
      )}

      {meta.telemetry && (
        <Card>
          <CardBody>
            <h3 className="mb-3 text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
              Pipeline Telemetry & Performance
            </h3>
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat label="Total Time" value={`${meta.telemetry.total_wall_time?.toFixed(1) || 0}s`} />
              <Stat label="LLM Calls" value={meta.performance_stats?.total_llm_calls || 0} />
              <Stat label="Cache Hit Rate" value={`${((meta.performance_stats?.cache_hit_rate || 0) * 100).toFixed(0)}%`} />
              <Stat label="Cost Est." value={`$${(meta.telemetry.total_cost || 0).toFixed(4)}`} />
            </dl>
          </CardBody>
        </Card>
      )}

      {ke.learning_objectives?.length > 0 && (
        <Card>
          <CardBody>
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
                Learning objectives
              </h3>
              <GroundingBadge origin="source" />
            </div>
            <ul className="space-y-2">
              {ke.learning_objectives.map((o, i) => (
                <li
                  key={i}
                  className="flex gap-2.5 text-[13.5px] leading-relaxed text-fg"
                >
                  <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[rgb(var(--accent))]" />
                  {o}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}

      {ke.prerequisites_list?.length > 0 && (
        <Card>
          <CardBody>
            <h3 className="mb-3 text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
              Assumed prior knowledge
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {ke.prerequisites_list.map((p, i) => (
                <Badge key={i} tone="neutral">
                  {p}
                </Badge>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardBody>
          <h3 className="mb-3 text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
            Generation details
          </h3>
          <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat
              label="Processing time"
              value={formatDuration(meta.processing_time_seconds)}
            />
            <Stat label="Model calls" value={meta.model_calls} />
            <Stat
              label="Tokens used"
              value={meta.total_tokens_used?.toLocaleString()}
            />
            <Stat label="Source pages" value={pkg.document_intelligence?.page_count} />
          </dl>
          {meta.models_used?.length > 0 && (
            <p className="mt-4 border-t border-default pt-3 font-mono text-[11.5px] text-fg-subtle">
              {meta.models_used.join(' · ')}
            </p>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

/* ── knowledge tab ────────────────────────────────────────────────────── */

function Knowledge({ ke }) {
  if (!ke?.concepts?.length) {
    return (
      <EmptyState
        icon={BookOpen}
        title="No concepts extracted"
        description="The extraction stage did not identify any concepts in this document."
      />
    )
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardBody>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
              Concepts ({ke.concepts.length})
            </h3>
            <GroundingBadge origin="source" />
          </div>
          <div className="space-y-3">
            {ke.concepts.map((c) => (
              <div
                key={c.id}
                className="border-b border-default pb-3 last:border-0 last:pb-0"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-[14px] font-semibold text-fg-strong">
                    {c.name}
                  </h4>
                  {c.is_core && <Badge tone="accent">Core</Badge>}
                  <Badge tone="neutral">{titleCase(c.difficulty)}</Badge>
                  <Badge tone="neutral">{titleCase(c.bloom_level)}</Badge>
                </div>
                {c.description && (
                  <p className="mt-1.5 text-[13.5px] leading-relaxed text-fg-subtle">
                    {c.description}
                  </p>
                )}
                {c.source_ref?.pages?.length > 0 && (
                  <p className="mt-1.5 font-mono text-[11.5px] text-fg-muted">
                    Source: page {c.source_ref.pages.join(', ')}
                  </p>
                )}
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      {ke.definitions?.length > 0 && (
        <Card>
          <CardBody>
            <h3 className="mb-3 text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
              Definitions ({ke.definitions.length})
            </h3>
            <dl className="space-y-3">
              {ke.definitions.map((d) => (
                <div key={d.id}>
                  <dt className="text-[13.5px] font-semibold text-fg-strong">
                    {d.term}
                  </dt>
                  <dd className="mt-0.5 text-[13.5px] leading-relaxed text-fg-subtle">
                    {d.text}
                  </dd>
                </div>
              ))}
            </dl>
          </CardBody>
        </Card>
      )}

      {ke.formulas?.length > 0 && (
        <Card>
          <CardBody>
            <h3 className="mb-3 text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
              Formulas ({ke.formulas.length})
            </h3>
            <div className="space-y-3">
              {ke.formulas.map((f) => (
                <div key={f.id}>
                  <p className="text-[13.5px] font-semibold text-fg-strong">
                    {f.name}
                  </p>
                  {f.latex && (
                    <pre className="mt-1 overflow-x-auto rounded-md border border-default bg-app-subtle px-3 py-2 font-mono text-[13px] text-fg">
                      {f.latex}
                    </pre>
                  )}
                  {f.explanation && (
                    <p className="mt-1 text-[13px] leading-relaxed text-fg-subtle">
                      {f.explanation}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}

      {ke.keywords?.length > 0 && (
        <Card>
          <CardBody>
            <h3 className="mb-3 text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
              Key terms
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {ke.keywords.map((k, i) => (
                <Badge key={i} tone="neutral">
                  {k}
                </Badge>
              ))}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}

/* ── exports tab ──────────────────────────────────────────────────────── */

function Exports({ jobId, available }) {
  const toast = useToast()

  const ICONS = {
    json: FileJson,
    'lesson-plan': ScrollText,
    'teacher-guide': BookOpen,
    assessments: ListChecks,
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {DOWNLOAD_FORMATS.map((fmt) => {
        const enabled = available.includes(fmt.id)
        const Icon = ICONS[fmt.id] || FileText

        return (
          <Card key={fmt.id} hover={enabled}>
            <CardBody className="flex items-center gap-3.5">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-fg">
                <Icon size={18} aria-hidden="true" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-medium text-fg-strong">
                  {fmt.label}
                </p>
                <p className="text-[12px] text-fg-subtle">{fmt.hint}</p>
              </div>
              <Button
                size="sm"
                variant={fmt.id === 'json' ? 'primary' : 'secondary'}
                disabled={!enabled}
                onClick={() => {
                  triggerDownload(jobId, fmt.id)
                  toast.success(`Downloading ${fmt.label}`)
                }}
              >
                <Download size={14} />
                Get
              </Button>
            </CardBody>
          </Card>
        )
      })}
    </div>
  )
}

/* ── page ─────────────────────────────────────────────────────────────── */

export default function Output() {
  const { jobId } = useParams()
  const [job, setJob] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('overview')

  useEffect(() => {
    let cancelled = false
    getJob(jobId)
      .then((data) => {
        if (cancelled) return
        if (!data.package) {
          setError(
            data.status === 'failed'
              ? data.error_message || 'This job failed before producing a package.'
              : 'This job has not finished generating yet.',
          )
        }
        setJob(data)
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [jobId])

  const pkg = job?.package
  const plan = pkg?.teaching_plan

  // Concept id → name, needed by nearly every panel to resolve references.
  const conceptNames = useMemo(() => {
    const map = {}
    for (const c of pkg?.knowledge_extraction?.concepts || []) {
      map[c.id] = c.name
    }
    return map
  }, [pkg])

  const contentByPeriod = useMemo(() => {
    const map = {}
    for (const c of pkg?.classroom_content || []) {
      map[c.period_id] = c
    }
    return map
  }, [pkg])

  const activitiesByPeriod = useMemo(() => {
    const map = {}
    for (const a of pkg?.activities || []) {
      for (const pid of a.linked_period_ids || []) {
        ;(map[pid] ||= []).push(a)
      }
    }
    return map
  }, [pkg])

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-9 w-72" />
        <div className="skeleton h-10 w-full" />
        <div className="skeleton h-64 w-full rounded-xl" />
      </div>
    )
  }

  if (error || !pkg) {
    return (
      <EmptyState
        icon={AlertCircle}
        title="Package unavailable"
        description={error || 'No package was found for this job.'}
        action={
          <div className="flex gap-2">
            <Link to="/app/library">
              <Button variant="secondary">Back to library</Button>
            </Link>
            <Link to="/app/upload">
              <Button>Upload a document</Button>
            </Link>
          </div>
        }
      />
    )
  }

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'knowledge', label: 'Knowledge', count: pkg.knowledge_extraction?.concepts?.length },
    { id: 'plan', label: 'Lesson plan', count: plan?.total_periods },
    { id: 'activities', label: 'Activities', count: pkg.activities?.length },
    {
      id: 'assessments',
      label: 'Assessments',
      count:
        (pkg.assessments?.items?.mcqs?.length || 0) +
        (pkg.assessments?.items?.short_answers?.length || 0) +
        (pkg.assessments?.items?.long_answers?.length || 0) +
        (pkg.assessments?.items?.numericals?.length || 0),
    },
    {
      id: 'gaps',
      label: 'Gap analysis',
      count: pkg.gap_analysis?.misconceptions?.length,
    },
    { id: 'exports', label: 'Export' },
  ]

  return (
    <div>
      <header className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="font-display text-2xl font-semibold tracking-tight text-fg-strong">
              {pkg.document_profile?.topic || job.file_name}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-[13px] text-fg-subtle">
              <FileText size={14} aria-hidden="true" />
              <span className="truncate">{job.file_name}</span>
            </div>
          </div>

          <Button
            size="sm"
            onClick={() => triggerDownload(jobId, 'json')}
          >
            <Download size={14} />
            Download JSON
          </Button>
        </div>
      </header>

      <Tabs tabs={tabs} active={tab} onChange={setTab} className="mb-6" />

      {tab === 'overview' && <Overview pkg={pkg} job={job} />}

      {tab === 'knowledge' && <Knowledge ke={pkg.knowledge_extraction} />}

      {tab === 'plan' && (
        <div className="space-y-3">
          {plan?.periods?.length ? (
            plan.periods.map((period, i) => (
              <PeriodCard
                key={period.id}
                period={period}
                content={contentByPeriod[period.id]}
                activities={activitiesByPeriod[period.id] || []}
                conceptNames={conceptNames}
                defaultOpen={i === 0}
              />
            ))
          ) : (
            <EmptyState
              icon={Layers}
              title="No teaching plan"
              description="The planning stage did not produce any periods."
            />
          )}
        </div>
      )}

      {tab === 'activities' && (
        <ActivityPanel
          activities={pkg.activities}
          periods={plan?.periods || []}
          conceptNames={conceptNames}
        />
      )}

      {tab === 'assessments' && (
        <AssessmentPanel
          assessments={pkg.assessments}
          conceptNames={conceptNames}
        />
      )}

      {tab === 'gaps' && (
        <GapPanel gapAnalysis={pkg.gap_analysis} conceptNames={conceptNames} />
      )}

      {tab === 'exports' && (
        <Exports jobId={jobId} available={job.available_downloads || []} />
      )}
    </div>
  )
}
