import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import {
  ArrowRight,
  Boxes,
  ClipboardList,
  FileSearch,
  FileText,
  GraduationCap,
  ListChecks,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Target,
  Upload,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { STAGE_META, STAGE_ORDER } from '@/lib/constants'
import { cn } from '@/lib/utils'

/* Scroll-reveal wrapper. Honours prefers-reduced-motion by rendering static. */
function Reveal({ children, delay = 0, className }) {
  const reduce = useReducedMotion()
  if (reduce) return <div className={className}>{children}</div>

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-80px' }}
      transition={{ duration: 0.55, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  )
}

function Section({ id, eyebrow, title, description, children, className }) {
  return (
    <section id={id} className={cn('container-content py-20 sm:py-28', className)}>
      <Reveal>
        <div className="mx-auto max-w-2xl text-center">
          {eyebrow && (
            <p className="mb-3 text-[12.5px] font-semibold uppercase tracking-[0.14em] text-accent-fg">
              {eyebrow}
            </p>
          )}
          <h2 className="text-display text-balance font-semibold text-fg-strong">
            {title}
          </h2>
          {description && (
            <p className="mx-auto mt-4 max-w-prose text-[16px] leading-relaxed text-fg-muted">
              {description}
            </p>
          )}
        </div>
      </Reveal>
      {children}
    </section>
  )
}

/* ── hero ─────────────────────────────────────────────────────────────── */

function Hero() {
  const reduce = useReducedMotion()
  const line = (delay) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 20 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.7, delay, ease: [0.22, 1, 0.36, 1] },
        }

  return (
    <section className="relative overflow-hidden">
      {/* Soft accent glow — subtle, single colour. */}
      <div
        className="pointer-events-none absolute inset-x-0 -top-40 h-[520px] opacity-60"
        style={{
          background:
            'radial-gradient(ellipse 60% 100% at 50% 0%, rgba(13,148,136,0.18), transparent 70%)',
        }}
        aria-hidden="true"
      />

      <div className="container-content relative pb-20 pt-20 sm:pb-28 sm:pt-28">
        <div className="mx-auto max-w-3xl text-center">
          <motion.div {...line(0)}>
            <span className="inline-flex items-center gap-2 rounded-full border border-accent-soft bg-accent-soft] px-3.5 py-1.5 text-[12.5px] font-medium text-accent-fg">
              <Sparkles size={13} aria-hidden="true" />
              Grounded in your source document
            </span>
          </motion.div>

          <motion.h1
            {...line(0.1)}
            className="mt-6 text-display-lg text-balance font-semibold text-fg-strong"
          >
            From chapter to classroom
          </motion.h1>

          <motion.p
            {...line(0.2)}
            className="mx-auto mt-5 max-w-prose text-[17px] leading-relaxed text-fg-muted"
          >
            Upload a textbook chapter and get a complete teaching package: an
            adaptive lesson plan, classroom scripts, activities, assessments and
            a misconception analysis — every fact traceable to your document.
          </motion.p>

          <motion.div
            {...line(0.3)}
            className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row"
          >
            <Link to="/app/upload">
              <Button size="lg" className="w-full sm:w-auto">
                <Upload size={17} />
                Upload a chapter
              </Button>
            </Link>
            <Link to="/app">
              <Button variant="secondary" size="lg" className="w-full sm:w-auto">
                Open the workspace
                <ArrowRight size={16} />
              </Button>
            </Link>
          </motion.div>
        </div>

        {/* Output preview panel */}
        <motion.div
          initial={reduce ? {} : { opacity: 0, y: 30 }}
          animate={reduce ? {} : { opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="mx-auto mt-16 max-w-4xl"
        >
          <div className="surface overflow-hidden p-1.5">
            <div className="rounded-lg bg-surface-sunken p-5 sm:p-7">
              <div className="mb-5 flex items-center gap-2.5">
                <FileText size={15} className="text-accent-fg" />
                <span className="font-mono text-[12.5px] text-fg-muted">
                  TeacherKnowledgePackage.json
                </span>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  { label: 'Periods', value: '4', hint: 'adaptive, not fixed' },
                  { label: 'Concepts', value: '12', hint: 'with source refs' },
                  { label: 'Grounding', value: '100%', hint: 'validated' },
                ].map((stat) => (
                  <div
                    key={stat.label}
                    className="rounded-lg border border-default bg-surface px-4 py-3.5"
                  >
                    <p className="text-[11px] font-medium uppercase tracking-wider text-fg-subtle">
                      {stat.label}
                    </p>
                    <p className="mt-1 font-display text-2xl font-semibold text-fg-strong">
                      {stat.value}
                    </p>
                    <p className="mt-0.5 text-[11.5px] text-fg-subtle">{stat.hint}</p>
                  </div>
                ))}
              </div>

              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {[
                  ['Lesson plan', ScrollText],
                  ['Activities', Boxes],
                  ['Assessments', ListChecks],
                  ['Gap analysis', Target],
                ].map(([label, Icon]) => (
                  <div
                    key={label}
                    className="flex items-center gap-2.5 rounded-lg border border-default bg-surface px-4 py-3"
                  >
                    <Icon size={15} className="text-accent-fg" aria-hidden="true" />
                    <span className="text-[13.5px] text-fg-muted">{label}</span>
                    <span className="ml-auto text-[11px] text-accent-fg">ready</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

/* ── how it works ─────────────────────────────────────────────────────── */

const STEPS = [
  {
    icon: Upload,
    title: 'Upload',
    text: 'Drop in a PDF, DOCX or text chapter. Tell us the document type so we route parsing efficiently.',
  },
  {
    icon: FileSearch,
    title: 'Understand',
    text: 'Gyantra parses structure, classifies the subject and grade, then extracts concepts and objectives.',
  },
  {
    icon: ClipboardList,
    title: 'Plan',
    text: 'An adaptive teaching plan is built from the content — the period count follows the material, not a template.',
  },
  {
    icon: GraduationCap,
    title: 'Generate',
    text: 'Scripts, board notes, activities, assessments and a misconception analysis for every period.',
  },
  {
    icon: ShieldCheck,
    title: 'Validate',
    text: 'Four checks confirm the package is complete, consistent and grounded before you export it.',
  },
]

function HowItWorks() {
  return (
    <Section
      eyebrow="How it works"
      title="Five steps, one upload"
      description="You answer a couple of quick questions. Gyantra handles the rest and shows its progress as it goes."
    >
      <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {STEPS.map((step, i) => (
          <Reveal key={step.title} delay={i * 0.07}>
            <div className="surface surface-hover h-full p-5">
              <div className="mb-3.5 flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent-fg">
                <step.icon size={17} aria-hidden="true" />
              </div>
              <p className="mb-1 font-mono text-[11px] text-fg-subtle">
                0{i + 1}
              </p>
              <h3 className="text-[15px] font-semibold text-fg-strong">
                {step.title}
              </h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-fg-muted">
                {step.text}
              </p>
            </div>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

/* ── pipeline ─────────────────────────────────────────────────────────── */

function Pipeline() {
  return (
    <Section
      eyebrow="The pipeline"
      title="Ten stages, not one prompt"
      description="Each stage has a defined input and output contract, is individually validated, and only receives the source it actually needs."
      className="border-y border-default/60"
    >
      <div className="mx-auto mt-14 max-w-3xl">
        {STAGE_ORDER.map((key, i) => (
          <Reveal key={key} delay={i * 0.04}>
            <div className="flex gap-4 pb-4">
              <div className="flex flex-col items-center">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-accent-soft bg-accent-soft] font-mono text-[12px] font-semibold text-accent-fg">
                  {i + 1}
                </div>
                {i < STAGE_ORDER.length - 1 && (
                  <span className="mt-1 h-full w-px flex-1 bg-app-subtle" aria-hidden="true" />
                )}
              </div>
              <div className="pb-2 pt-1.5">
                <h3 className="text-[14.5px] font-semibold text-fg-strong">
                  {STAGE_META[key].label}
                </h3>
                <p className="mt-0.5 text-[13px] leading-relaxed text-fg-subtle">
                  {STAGE_META[key].blurb}
                </p>
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

/* ── grounding ────────────────────────────────────────────────────────── */

function Grounding() {
  return (
    <Section
      eyebrow="Why you can trust it"
      title="Grounded, not guessed"
      description="The hardest problem in AI-generated teaching material is invented facts. Gyantra treats grounding as an architectural constraint, not a prompt instruction."
    >
      <div className="mx-auto mt-14 grid max-w-4xl gap-4 sm:grid-cols-2">
        {[
          {
            icon: ShieldCheck,
            title: 'Source-locked facts',
            text: 'Concepts, definitions and formulas are extracted from your document and carry references back to the page and section they came from.',
          },
          {
            icon: Sparkles,
            title: 'Separated scaffolding',
            text: 'Analogies, activities and motivational content are labelled as pedagogical support, so you always know what came from the source and what did not.',
          },
          {
            icon: FileSearch,
            title: 'Automated audit',
            text: 'A lexical pre-filter flags claims that introduce unfamiliar subject vocabulary, then a model audits the shortlist for genuine drift.',
          },
          {
            icon: ListChecks,
            title: 'Reported, not hidden',
            text: 'The validation panel shows every warning it found. You see the hallucination risk figure and the specific claims worth a second look.',
          },
        ].map((item, i) => (
          <Reveal key={item.title} delay={i * 0.07}>
            <div className="surface h-full p-6">
              <div className="mb-3.5 flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent-fg">
                <item.icon size={17} aria-hidden="true" />
              </div>
              <h3 className="text-[15px] font-semibold text-fg-strong">
                {item.title}
              </h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-fg-muted">
                {item.text}
              </p>
            </div>
          </Reveal>
        ))}
      </div>
    </Section>
  )
}

/* ── CTA ──────────────────────────────────────────────────────────────── */

function CallToAction() {
  return (
    <section className="container-content pb-24 pt-8">
      <Reveal>
        <div className="surface relative overflow-hidden px-6 py-14 text-center sm:px-12">
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                'radial-gradient(ellipse 70% 100% at 50% 0%, rgba(13,148,136,0.13), transparent 70%)',
            }}
            aria-hidden="true"
          />
          <div className="relative">
            <h2 className="text-display text-balance font-semibold text-fg-strong">
              Turn your next chapter into a lesson
            </h2>
            <p className="mx-auto mt-4 max-w-prose text-[16px] leading-relaxed text-fg-muted">
              Upload a document and review the generated package. No setup, no
              account required.
            </p>
            <Link to="/app/upload" className="mt-8 inline-block">
              <Button size="lg">
                <Upload size={17} />
                Upload a chapter
              </Button>
            </Link>
          </div>
        </div>
      </Reveal>
    </section>
  )
}

export default function Landing() {
  return (
    <>
      <Hero />
      <HowItWorks />
      <Pipeline />
      <Grounding />
      <CallToAction />
    </>
  )
}
