import {
  BookOpen,
  ClipboardCheck,
  Clock,
  Heart,
  HelpCircle,
  Home,
  PenLine,
  Presentation,
  Sparkles,
  Target,
} from 'lucide-react'
import { Disclosure } from '@/components/ui/Disclosure'
import { Badge, GroundingBadge } from '@/components/ui/Badge'
import { toParagraphs } from '@/lib/utils'
import { ACTIVITY_LABELS } from '@/lib/constants'

function Section({ icon: Icon, title, children, note }) {
  return (
    <section className="py-3.5 first:pt-0 last:pb-0">
      <div className="mb-2 flex items-center gap-2">
        <Icon size={14} className="text-accent-fg" aria-hidden="true" />
        <h4 className="text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
          {title}
        </h4>
        {note}
      </div>
      {children}
    </section>
  )
}

function Prose({ text }) {
  const paragraphs = toParagraphs(text)
  if (!paragraphs.length) {
    return <p className="text-[13px] italic text-fg-subtle">Not generated.</p>
  }
  return (
    <div className="teaching-prose">
      {paragraphs.map((p, i) => (
        <p key={i}>{p}</p>
      ))}
    </div>
  )
}

/** Board notes are a copyable outline, so they render monospaced. */
function BoardNotes({ text }) {
  const lines = toParagraphs(text)
  if (!lines.length) {
    return <p className="text-[13px] italic text-fg-subtle">Not generated.</p>
  }
  return (
    <div className="rounded-lg border border-default bg-surface-sunken p-3.5">
      <pre className="whitespace-pre-wrap font-mono text-[12.5px] leading-relaxed text-fg-muted">
        {lines.join('\n')}
      </pre>
    </div>
  )
}

function QuestionList({ items }) {
  if (!items?.length) {
    return <p className="text-[13px] italic text-fg-subtle">None generated.</p>
  }
  return (
    <ol className="space-y-1.5">
      {items.map((q, i) => (
        <li key={i} className="flex gap-2.5 text-[13.5px] leading-relaxed text-fg-muted">
          <span className="mt-0.5 shrink-0 font-mono text-[11px] text-fg-subtle">
            {i + 1}.
          </span>
          <span>{q}</span>
        </li>
      ))}
    </ol>
  )
}

/**
 * One teaching period, collapsed by default beyond the first.
 * Everything the teacher needs to deliver the class is inside.
 */
export function PeriodCard({
  period,
  content,
  activities = [],
  conceptNames = {},
  defaultOpen = false,
}) {
  const objectives = period.objectives || []
  const concepts = (period.key_concepts || [])
    .map((id) => conceptNames[id])
    .filter(Boolean)

  return (
    <Disclosure
      defaultOpen={defaultOpen}
      title={`Period ${period.number}: ${period.title}`}
      subtitle={period.flow_summary}
      badge={
        <Badge tone="neutral" icon={Clock}>
          {period.estimated_minutes} min
        </Badge>
      }
    >
      <div className="divide-y divide-[rgb(var(--border))]">
        {objectives.length > 0 && (
          <Section icon={Target} title="Learning objectives">
            <ul className="space-y-1.5">
              {objectives.map((o, i) => (
                <li
                  key={i}
                  className="flex gap-2.5 text-[13.5px] leading-relaxed text-fg-muted"
                >
                  <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[rgb(var(--accent))]" />
                  <span>{typeof o === 'string' ? o : o.text}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {concepts.length > 0 && (
          <Section icon={BookOpen} title="Concepts covered">
            <div className="flex flex-wrap gap-1.5">
              {concepts.map((name, i) => (
                <Badge key={i} tone="accent">
                  {name}
                </Badge>
              ))}
            </div>
          </Section>
        )}

        {period.prerequisite_review?.length > 0 && (
          <Section icon={ClipboardCheck} title="Review first">
            <ul className="space-y-1">
              {period.prerequisite_review.map((r, i) => (
                <li key={i} className="text-[13.5px] leading-relaxed text-fg-muted">
                  {r}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {content && (
          <>
            <Section icon={Sparkles} title="Entry ticket / warm-up">
              <Prose text={content.warmup} />
            </Section>

            <Section icon={Presentation} title="Teacher script">
              <Prose text={content.teacher_script} />
            </Section>

            <Section icon={PenLine} title="Blackboard notes">
              <BoardNotes text={content.blackboard_notes} />
            </Section>

            <Section icon={HelpCircle} title="Checkpoint questions">
              <QuestionList items={content.checkpoint_questions} />
            </Section>

            <Section icon={ClipboardCheck} title="Exit ticket">
              <Prose text={content.exit_ticket} />
            </Section>

            <Section icon={Home} title="Homework">
              <Prose text={content.homework} />
            </Section>

            {content.mentor_moment && (
              <Section
                icon={Heart}
                title="Mentor moment"
                note={<GroundingBadge origin="pedagogical" />}
              >
                <blockquote className="border-l-2 border-accent-soft pl-3.5 text-[13.5px] italic leading-relaxed text-fg-muted">
                  {content.mentor_moment}
                </blockquote>
              </Section>
            )}
          </>
        )}

        {activities.length > 0 && (
          <Section icon={Sparkles} title="Activities for this period">
            <ul className="space-y-1.5">
              {activities.map((a) => (
                <li
                  key={a.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-default px-3 py-2"
                >
                  <span className="min-w-0 truncate text-[13.5px] text-fg">
                    {a.title}
                  </span>
                  <span className="shrink-0 text-[11.5px] text-fg-subtle">
                    {ACTIVITY_LABELS[a.activity_type] || a.activity_type} ·{' '}
                    {a.duration_minutes}m
                  </span>
                </li>
              ))}
            </ul>
          </Section>
        )}
      </div>
    </Disclosure>
  )
}
