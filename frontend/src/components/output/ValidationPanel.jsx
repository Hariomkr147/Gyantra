import {
  AlertTriangle,
  CheckCircle2,
  FileWarning,
  Link2,
  ShieldCheck,
  XCircle,
} from 'lucide-react'
import { Card, CardBody, EmptyState } from '@/components/ui/Card'
import { ValidationPill } from '@/components/ui/Badge'
import { cn, pct, titleCase } from '@/lib/utils'

const CHECKS = [
  {
    key: 'schema_check',
    icon: FileWarning,
    label: 'Schema',
    blurb: 'Required fields present and correctly typed',
    listKey: 'missing_fields',
    listLabel: 'Missing fields',
  },
  {
    key: 'consistency_check',
    icon: Link2,
    label: 'Consistency',
    blurb: 'References line up across pipeline stages',
    listKey: 'issues',
    listLabel: 'Issues',
  },
  {
    key: 'pedagogical_check',
    icon: CheckCircle2,
    label: 'Pedagogy',
    blurb: 'Coverage, Bloom spread and activity variety',
    listKey: 'notes',
    listLabel: 'Notes',
  },
  {
    key: 'grounding_check',
    icon: ShieldCheck,
    label: 'Grounding',
    blurb: 'Content stays inside the source document scope',
    listKey: 'ungrounded_claims',
    listLabel: 'Claims to review',
  },
]

const STATUS_ICON = { pass: CheckCircle2, warn: AlertTriangle, fail: XCircle }
const STATUS_COLOR = {
  pass: 'text-success',
  warn: 'text-warn',
  fail: 'text-danger',
}

function CheckCard({ check, data }) {
  const status = data?.status || 'warn'
  const Icon = check.icon
  const StatusIcon = STATUS_ICON[status] || AlertTriangle
  const items = data?.[check.listKey] || []

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2.5">
            <Icon
              size={16}
              className={cn('mt-0.5 shrink-0', STATUS_COLOR[status])}
              aria-hidden="true"
            />
            <div className="min-w-0">
              <h4 className="text-[14px] font-semibold text-fg-strong">
                {check.label}
              </h4>
              <p className="mt-0.5 text-[12.5px] leading-snug text-fg-subtle">
                {check.blurb}
              </p>
            </div>
          </div>
          <ValidationPill status={status} className="shrink-0" />
        </div>

        {/* Grounding gets a numeric risk read-out. */}
        {check.key === 'grounding_check' &&
          typeof data?.hallucination_risk === 'number' && (
            <div className="rounded-lg border border-default bg-surface-sunken px-3 py-2">
              <div className="flex items-center justify-between text-[12.5px]">
                <span className="text-fg-muted">Hallucination risk</span>
                <span
                  className={cn(
                    'font-mono font-semibold tabular-nums',
                    data.hallucination_risk > 0.25
                      ? 'text-danger'
                      : data.hallucination_risk > 0.08
                        ? 'text-warn'
                        : 'text-success',
                  )}
                >
                  {pct(data.hallucination_risk)}
                </span>
              </div>
              <div className="mt-2 h-1 overflow-hidden rounded-full bg-app-subtle">
                <div
                  className={cn(
                    'h-full rounded-full transition-all',
                    data.hallucination_risk > 0.25
                      ? 'bg-[rgb(var(--danger-fg))]'
                      : data.hallucination_risk > 0.08
                        ? 'bg-[rgb(var(--warn-fg))]'
                        : 'bg-[rgb(var(--success-fg))]',
                  )}
                  style={{
                    width: `${Math.min(100, data.hallucination_risk * 100)}%`,
                  }}
                />
              </div>
            </div>
          )}

        {/* Bloom distribution for the pedagogical check. */}
        {check.key === 'pedagogical_check' &&
          data?.bloom_distribution &&
          Object.keys(data.bloom_distribution).length > 0 && (
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {Object.entries(data.bloom_distribution).map(([level, n]) => (
                <span key={level} className="text-[11.5px] text-fg-subtle">
                  {titleCase(level)} · {n}
                </span>
              ))}
            </div>
          )}

        {items.length > 0 && (
          <div>
            <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-fg-subtle">
              {check.listLabel} ({items.length})
            </p>
            <ul className="space-y-1.5">
              {items.slice(0, 8).map((item, i) => (
                <li
                  key={i}
                  className="flex gap-2 text-[12.5px] leading-relaxed text-fg-muted"
                >
                  <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-app-subtle" />
                  <span className="min-w-0 break-words">{item}</span>
                </li>
              ))}
              {items.length > 8 && (
                <li className="pl-3 text-[12px] italic text-fg-subtle">
                  and {items.length - 8} more
                </li>
              )}
            </ul>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

export function ValidationPanel({ validation }) {
  if (!validation) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="No validation record"
        description="Validation did not run for this job."
      />
    )
  }

  const overall = validation.overall_status || 'warn'
  const OverallIcon = STATUS_ICON[overall] || AlertTriangle

  return (
    <div className="space-y-4">
      {/* Overall banner */}
      <Card
        className={cn(
          'border-l-2',
          overall === 'pass'
            ? 'border-l-[rgb(var(--success-fg))]'
            : overall === 'warn'
              ? 'border-l-[rgb(var(--warn-fg))]'
              : 'border-l-[rgb(var(--danger-fg))]',
        )}
      >
        <CardBody className="flex items-start gap-3.5">
          <OverallIcon
            size={20}
            className={cn('mt-0.5 shrink-0', STATUS_COLOR[overall])}
            aria-hidden="true"
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <h3 className="text-[15px] font-semibold text-fg-strong">
                Validation {overall === 'pass' ? 'passed' : overall === 'warn' ? 'passed with warnings' : 'failed'}
              </h3>
              <ValidationPill status={overall} />
            </div>
            <p className="mt-1 text-[13px] leading-relaxed text-fg-muted">
              {overall === 'pass'
                ? 'All four checks passed. The package is schema-valid, internally consistent, and grounded in the source document.'
                : overall === 'warn'
                  ? 'The package is usable, but some checks raised warnings worth a quick review before classroom use.'
                  : 'One or more checks failed. Review the details below before using this package.'}
            </p>
          </div>
        </CardBody>
      </Card>

      <div className="grid gap-3 lg:grid-cols-2">
        {CHECKS.map((check) => (
          <CheckCard key={check.key} check={check} data={validation[check.key]} />
        ))}
      </div>

      {validation.regen_suggestions?.length > 0 && (
        <Card>
          <CardBody>
            <h4 className="mb-2 text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
              Suggested next steps
            </h4>
            <ul className="space-y-1.5">
              {validation.regen_suggestions.map((s, i) => (
                <li
                  key={i}
                  className="flex gap-2 text-[13px] leading-relaxed text-fg-muted"
                >
                  <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[rgb(var(--accent))]" />
                  {s}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
