import { useMemo, useState } from 'react'
import { CheckCircle2, Eye, EyeOff, ListChecks } from 'lucide-react'
import { EmptyState } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Disclosure } from '@/components/ui/Disclosure'
import { cn, titleCase, toParagraphs } from '@/lib/utils'
import { BLOOM_ORDER } from '@/lib/constants'

const BLOOM_TONE = {
  remember: 'neutral',
  understand: 'neutral',
  apply: 'accent',
  analyze: 'accent',
  evaluate: 'warn',
  create: 'warn',
}

/**
 * Normalise the four typed question arrays into one render shape.
 * The backend keeps them separate (different fields per type); the UI only
 * needs a common surface, so the mapping lives here rather than in each view.
 */
function normalise(items) {
  const sections = []

  if (items.mcqs?.length) {
    sections.push({
      id: 'mcqs',
      title: 'Section A — Multiple Choice',
      typeLabel: 'MCQ',
      questions: items.mcqs.map((q) => ({
        id: q.id,
        prompt: q.stem,
        options: q.options || [],
        correctKey: q.correct_key,
        explanation: q.explanation,
        marks: q.marks,
        bloom: q.bloom_level,
        difficulty: q.difficulty,
        conceptIds: q.linked_concept_ids || [],
      })),
    })
  }

  if (items.short_answers?.length) {
    sections.push({
      id: 'short',
      title: 'Section B — Short Answer',
      typeLabel: 'Short answer',
      questions: items.short_answers.map((q) => ({
        id: q.id,
        prompt: q.question,
        answer: q.model_answer,
        keyPoints: q.key_points || [],
        marks: q.marks,
        conceptIds: q.linked_concept_ids || [],
        rubric: q.rubric,
      })),
    })
  }

  if (items.numericals?.length) {
    sections.push({
      id: 'numerical',
      title: 'Section C — Numerical Problems',
      typeLabel: 'Numerical',
      questions: items.numericals.map((q) => ({
        id: q.id,
        prompt: q.question,
        answer: [q.answer, q.unit].filter(Boolean).join(' '),
        steps: q.solution_steps || [],
        marks: q.marks,
        conceptIds: q.linked_concept_ids || [],
      })),
    })
  }

  if (items.long_answers?.length) {
    sections.push({
      id: 'long',
      title: 'Section D — Long Answer',
      typeLabel: 'Long answer',
      questions: items.long_answers.map((q) => ({
        id: q.id,
        prompt: q.question,
        markingScheme: q.marking_scheme,
        wordLimit: q.word_limit,
        marks: q.marks,
        conceptIds: q.linked_concept_ids || [],
        rubric: q.rubric,
      })),
    })
  }

  return sections
}

function QuestionRow({ question, index, typeLabel, showAnswers, conceptNames }) {
  const concepts = (question.conceptIds || [])
    .map((id) => conceptNames[id])
    .filter(Boolean)

  return (
    <li className="border-b border-default py-4 first:pt-0 last:border-0 last:pb-0">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 shrink-0 font-mono text-[11.5px] text-fg-subtle">
          {String(index + 1).padStart(2, '0')}
        </span>

        <div className="min-w-0 flex-1">
          <p className="text-[14px] leading-relaxed text-fg-strong">
            {question.prompt}
          </p>

          {question.options?.length > 0 && (
            <ol className="mt-2.5 space-y-1.5">
              {question.options.map((opt) => {
                const correct =
                  showAnswers &&
                  String(question.correctKey || '').toUpperCase() ===
                    String(opt.key || '').toUpperCase()

                return (
                  <li
                    key={opt.key}
                    className={cn(
                      'flex items-start gap-2.5 rounded-md border px-2.5 py-1.5',
                      'text-[13px] leading-relaxed transition-colors',
                      correct
                        ? 'border-[rgb(var(--success-fg)/0.3)] bg-[rgb(var(--success-fg)/0.1)]] text-success'
                        : 'border-default text-fg-muted',
                    )}
                  >
                    <span className="shrink-0 font-mono text-[11px] text-fg-subtle">
                      {opt.key}
                    </span>
                    <span className="min-w-0 flex-1">{opt.text}</span>
                    {correct && (
                      <CheckCircle2
                        size={13}
                        className="mt-0.5 shrink-0 text-success"
                        aria-label="Correct answer"
                      />
                    )}
                  </li>
                )
              })}
            </ol>
          )}

          {showAnswers && question.answer && (
            <div className="mt-2.5 rounded-lg border border-[rgb(var(--success-fg)/0.3)] bg-[rgb(var(--success-fg)/0.1)]] px-3 py-2">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-success">
                Expected answer
              </p>
              <div className="teaching-prose text-[13px] text-success">
                {toParagraphs(question.answer).map((p, i) => (
                  <p key={i}>{p}</p>
                ))}
              </div>
            </div>
          )}

          {showAnswers && question.keyPoints?.length > 0 && (
            <ul className="mt-2 space-y-1">
              {question.keyPoints.map((kp, i) => (
                <li key={i} className="flex gap-2 text-[12.5px] text-fg-muted">
                  <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-app-subtle" />
                  {kp}
                </li>
              ))}
            </ul>
          )}

          {showAnswers && question.steps?.length > 0 && (
            <ol className="mt-2 space-y-1">
              {question.steps.map((s, i) => (
                <li key={i} className="flex gap-2 text-[12.5px] text-fg-muted">
                  <span className="shrink-0 font-mono text-[11px] text-fg-subtle">
                    {i + 1}.
                  </span>
                  {s}
                </li>
              ))}
            </ol>
          )}

          {showAnswers && question.markingScheme && (
            <p className="mt-2 rounded-lg border border-default bg-surface-sunken px-3 py-2 text-[12.5px] leading-relaxed text-fg-muted">
              <span className="font-medium text-fg-muted">Marking scheme: </span>
              {question.markingScheme}
            </p>
          )}

          {showAnswers && question.explanation && (
            <p className="mt-2 text-[12.5px] leading-relaxed text-fg-subtle">
              <span className="font-medium text-fg-muted">Why: </span>
              {question.explanation}
            </p>
          )}

          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            <Badge tone="neutral">{typeLabel}</Badge>
            <Badge tone="neutral">
              {question.marks} mark{question.marks === 1 ? '' : 's'}
            </Badge>
            {question.bloom && (
              <Badge tone={BLOOM_TONE[question.bloom] || 'neutral'}>
                {titleCase(question.bloom)}
              </Badge>
            )}
            {question.difficulty && (
              <Badge tone="neutral">{titleCase(question.difficulty)}</Badge>
            )}
            {question.wordLimit && (
              <Badge tone="neutral">~{question.wordLimit} words</Badge>
            )}
            {concepts.map((name, i) => (
              <Badge key={i} tone="accent">
                {name}
              </Badge>
            ))}
          </div>
        </div>
      </div>
    </li>
  )
}

function BlueprintBar({ blueprint }) {
  const entries = BLOOM_ORDER.map((level) => [level, blueprint[level] || 0]).filter(
    ([, marks]) => marks > 0,
  )
  if (!entries.length) return null

  const total = entries.reduce((n, [, m]) => n + m, 0)

  return (
    <div className="surface p-4">
      <h4 className="mb-3 text-[12.5px] font-semibold uppercase tracking-wider text-fg-muted">
        Bloom's distribution
      </h4>
      <div className="flex h-2 overflow-hidden rounded-full bg-app-subtle">
        {entries.map(([level, marks]) => (
          <div
            key={level}
            className={cn(
              'h-full',
              BLOOM_TONE[level] === 'warn'
                ? 'bg-[rgb(var(--warn-fg))]'
                : BLOOM_TONE[level] === 'accent'
                  ? 'bg-[rgb(var(--accent))]'
                  : 'bg-[rgb(var(--accent))]',
            )}
            style={{ width: `${(marks / total) * 100}%` }}
            title={`${titleCase(level)}: ${marks} marks`}
          />
        ))}
      </div>
      <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1">
        {entries.map(([level, marks]) => (
          <span key={level} className="text-[11.5px] text-fg-subtle">
            {titleCase(level)} · {marks}
          </span>
        ))}
      </div>
    </div>
  )
}

export function AssessmentPanel({ assessments, conceptNames = {} }) {
  const [showAnswers, setShowAnswers] = useState(false)
  const items = assessments?.items
  const sections = useMemo(() => (items ? normalise(items) : []), [items])

  if (!sections.length) {
    return (
      <EmptyState
        icon={ListChecks}
        title="No assessments generated"
        description="The assessment stage did not produce any questions for this document."
      />
    )
  }

  const totalQuestions = sections.reduce((n, s) => n + s.questions.length, 0)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-fg-muted">
          {totalQuestions} question{totalQuestions === 1 ? '' : 's'} across{' '}
          {sections.length} section{sections.length === 1 ? '' : 's'} ·{' '}
          {items.total_marks} marks
        </p>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setShowAnswers((v) => !v)}
        >
          {showAnswers ? <EyeOff size={14} /> : <Eye size={14} />}
          {showAnswers ? 'Hide answer key' : 'Show answer key'}
        </Button>
      </div>

      {assessments.blueprint && Object.keys(assessments.blueprint).length > 0 && (
        <BlueprintBar blueprint={assessments.blueprint} />
      )}

      <div className="space-y-3">
        {sections.map((section, i) => {
          const marks = section.questions.reduce((n, q) => n + (q.marks || 0), 0)
          return (
            <Disclosure
              key={section.id}
              defaultOpen={i === 0}
              title={section.title}
              subtitle={`${section.questions.length} question${
                section.questions.length === 1 ? '' : 's'
              } · ${marks} marks`}
            >
              <ul>
                {section.questions.map((q, qi) => (
                  <QuestionRow
                    key={q.id || qi}
                    question={q}
                    index={qi}
                    typeLabel={section.typeLabel}
                    showAnswers={showAnswers}
                    conceptNames={conceptNames}
                  />
                ))}
              </ul>
            </Disclosure>
          )
        })}
      </div>
    </div>
  )
}
