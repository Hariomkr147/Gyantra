import { AlertTriangle, HelpCircle, Stethoscope, Wrench } from 'lucide-react'
import { Card, CardBody, EmptyState } from '@/components/ui/Card'
import { Badge, SeverityPill } from '@/components/ui/Badge'
import { cn, pct } from '@/lib/utils'

const SEVERITY_ORDER = { high: 0, medium: 1, low: 2 }

function Field({ icon: Icon, label, children }) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5">
        <Icon size={12} className="text-fg-subtle" aria-hidden="true" />
        <h5 className="text-[11px] font-semibold uppercase tracking-wider text-fg-subtle">
          {label}
        </h5>
      </div>
      <p className="text-[13.5px] leading-relaxed text-fg-muted">{children}</p>
    </div>
  )
}

/**
 * Learning-gap analysis: each likely misconception with its diagnostic and
 * remedy. Sorted by severity so the blocking problems appear first.
 */
export function GapPanel({ gapAnalysis, conceptNames = {} }) {
  const misconceptions = gapAnalysis?.misconceptions || []

  if (!misconceptions.length) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="No gap analysis available"
        description="The learning-gap stage did not produce any misconceptions for this document."
      />
    )
  }

  const sorted = [...misconceptions].sort(
    (a, b) =>
      (SEVERITY_ORDER[a.severity] ?? 1) - (SEVERITY_ORDER[b.severity] ?? 1),
  )

  const counts = misconceptions.reduce((acc, m) => {
    acc[m.severity] = (acc[m.severity] || 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[13px] text-fg-muted">
          {misconceptions.length} likely misconception
          {misconceptions.length === 1 ? '' : 's'}
        </p>
        <span className="text-fg">·</span>
        {['high', 'medium', 'low'].map(
          (s) =>
            counts[s] > 0 && (
              <span key={s} className="text-[12.5px] text-fg-subtle">
                {counts[s]} {s}
              </span>
            ),
        )}
        {gapAnalysis.coverage_score > 0 && (
          <>
            <span className="text-fg">·</span>
            <span className="text-[12.5px] text-fg-subtle">
              {pct(gapAnalysis.coverage_score)} concept coverage
            </span>
          </>
        )}
      </div>

      {gapAnalysis.remediation_summary && (
        <Card>
          <CardBody>
            <h4 className="mb-1.5 text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
              Overall pattern
            </h4>
            <p className="text-[13.5px] leading-relaxed text-fg-muted">
              {gapAnalysis.remediation_summary}
            </p>
          </CardBody>
        </Card>
      )}

      <div className="space-y-3">
        {sorted.map((m, i) => {
          const concepts = (m.linked_concept_ids || [])
            .map((id) => conceptNames[id])
            .filter(Boolean)

          return (
            <Card
              key={m.id || i}
              className={cn(
                'border-l-2',
                m.severity === 'high'
                  ? 'border-l-[rgb(var(--danger-fg))]'
                  : m.severity === 'medium'
                    ? 'border-l-[rgb(var(--warn-fg))]'
                    : 'border-l-[rgb(var(--accent))]',
              )}
            >
              <CardBody className="space-y-3.5">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-[14px] font-medium leading-relaxed text-fg-strong">
                    {m.misconception}
                  </p>
                  <SeverityPill severity={m.severity} className="mt-0.5 shrink-0" />
                </div>

                {m.diagnostic_question && (
                  <Field icon={HelpCircle} label="Diagnostic question">
                    {m.diagnostic_question}
                  </Field>
                )}

                {m.expected_wrong_answer && (
                  <Field icon={Stethoscope} label="Answer that reveals it">
                    {m.expected_wrong_answer}
                  </Field>
                )}

                {m.remedial_action && (
                  <Field icon={Wrench} label="Remediation">
                    {m.remedial_action}
                  </Field>
                )}

                {concepts.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 pt-0.5">
                    {concepts.map((name, ci) => (
                      <Badge key={ci} tone="accent">
                        {name}
                      </Badge>
                    ))}
                  </div>
                )}
              </CardBody>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
