import { Clock, Package, Sparkles, Target, Users } from 'lucide-react'
import { EmptyState } from '@/components/ui/Card'
import { Badge, GroundingBadge } from '@/components/ui/Badge'
import { Disclosure } from '@/components/ui/Disclosure'
import { toParagraphs } from '@/lib/utils'
import { ACTIVITY_LABELS } from '@/lib/constants'

function Row({ icon: Icon, label, children }) {
  return (
    <div className="py-3 first:pt-0 last:pb-0">
      <div className="mb-1.5 flex items-center gap-2">
        <Icon size={13} className="text-accent-fg" aria-hidden="true" />
        <h4 className="text-[12px] font-semibold uppercase tracking-wider text-fg-muted">
          {label}
        </h4>
      </div>
      {children}
    </div>
  )
}

export function ActivityPanel({ activities = [], periods = [], conceptNames = {} }) {
  if (!activities.length) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No activities generated"
        description="The activity stage did not produce any classroom tasks for this document."
      />
    )
  }

  const periodNumbers = Object.fromEntries(
    periods.map((p) => [p.id, p.number]),
  )
  const typeCount = new Set(activities.map((a) => a.activity_type)).size

  return (
    <div className="space-y-4">
      <p className="text-[13px] text-fg-muted">
        {activities.length} activit{activities.length === 1 ? 'y' : 'ies'} across{' '}
        {typeCount} type{typeCount === 1 ? '' : 's'}
      </p>

      <div className="space-y-3">
        {activities.map((activity, i) => {
          const linkedPeriods = (activity.linked_period_ids || [])
            .map((id) => periodNumbers[id])
            .filter(Boolean)
            .sort((a, b) => a - b)

          const concepts = (activity.linked_concept_ids || [])
            .map((id) => conceptNames[id])
            .filter(Boolean)

          return (
            <Disclosure
              key={activity.id || i}
              defaultOpen={i === 0}
              title={activity.title}
              subtitle={
                linkedPeriods.length
                  ? `Period ${linkedPeriods.join(', ')}`
                  : 'Not tied to a specific period'
              }
              badge={
                <div className="flex shrink-0 items-center gap-1.5">
                  <Badge tone="accent">
                    {ACTIVITY_LABELS[activity.activity_type] ||
                      activity.activity_type}
                  </Badge>
                  <Badge tone="neutral" icon={Clock}>
                    {activity.duration_minutes}m
                  </Badge>
                </div>
              }
            >
              <div className="divide-y divide-[rgb(var(--border))]">
                {activity.materials?.length > 0 && (
                  <Row icon={Package} label="Materials">
                    <div className="flex flex-wrap gap-1.5">
                      {activity.materials.map((m, mi) => (
                        <Badge key={mi} tone="neutral">
                          {m}
                        </Badge>
                      ))}
                    </div>
                  </Row>
                )}

                {activity.teacher_instructions && (
                  <Row icon={Users} label="Teacher instructions">
                    <div className="teaching-prose">
                      {toParagraphs(activity.teacher_instructions).map((p, pi) => (
                        <p key={pi}>{p}</p>
                      ))}
                    </div>
                  </Row>
                )}

                {activity.expected_student_response && (
                  <Row icon={Target} label="Expected student response">
                    <p className="text-[13.5px] leading-relaxed text-fg-muted">
                      {activity.expected_student_response}
                    </p>
                  </Row>
                )}

                {activity.success_criteria && (
                  <Row icon={Target} label="Success criteria">
                    <p className="text-[13.5px] leading-relaxed text-fg-muted">
                      {activity.success_criteria}
                    </p>
                  </Row>
                )}

                <div className="flex flex-wrap items-center gap-1.5 pt-3">
                  <GroundingBadge origin="pedagogical" />
                  {concepts.map((name, ci) => (
                    <Badge key={ci} tone="accent">
                      {name}
                    </Badge>
                  ))}
                </div>
              </div>
            </Disclosure>
          )
        })}
      </div>
    </div>
  )
}
