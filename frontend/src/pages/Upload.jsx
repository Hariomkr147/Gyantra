import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, ChevronDown, Info, Upload as UploadIcon } from 'lucide-react'
import { Card, CardBody } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Field, OptionCards, Select, TextInput } from '@/components/ui/Form'
import { Dropzone } from '@/components/upload/Dropzone'
import { useToast } from '@/components/ui/Toast'
import { getConfigOptions, uploadDocument } from '@/lib/api'
import {
  ASSESSMENT_DEPTHS,
  DOCUMENT_HINTS,
  TEACHING_STYLES,
  OUTPUT_LANGUAGES,
} from '@/lib/constants'

const GRADES = [
  { value: '', label: 'Let Gyantra infer it' },
  ...Array.from({ length: 7 }, (_, i) => ({
    value: `Class ${i + 6}`,
    label: `Class ${i + 6}`,
  })),
  { value: 'Undergraduate', label: 'Undergraduate' },
]

const BOARDS = [
  { value: '', label: 'Not specified' },
  { value: 'CBSE', label: 'CBSE' },
  { value: 'ICSE', label: 'ICSE' },
  { value: 'NCERT', label: 'NCERT' },
  { value: 'State Board', label: 'State Board' },
  { value: 'IB', label: 'IB' },
  { value: 'Common Core', label: 'Common Core' },
]

export default function Upload() {
  const navigate = useNavigate()
  const toast = useToast()

  const [file, setFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [limits, setLimits] = useState({
    maxSizeMb: 25,
    extensions: ['.pdf', '.docx', '.txt', '.md'],
  })

  const [form, setForm] = useState({
    document_hint: 'not_sure',
    language: 'en',
    subject: '',
    grade: '',
    board: '',
    teaching_style: '',
    assessment_depth: 'balanced',
    period_minutes: '',
    total_periods_available: '',
    time_constraints: '',
  })

  const set = (key) => (e) =>
    setForm((f) => ({ ...f, [key]: e?.target ? e.target.value : e }))

  // Pull real limits from the backend so the two can't drift.
  useEffect(() => {
    getConfigOptions()
      .then((opts) => {
        setLimits({
          maxSizeMb: opts.max_file_size_mb ?? 25,
          extensions: opts.supported_extensions ?? limits.extensions,
        })
      })
      .catch(() => {
        // Non-fatal: the defaults above are reasonable and the server
        // re-validates anyway.
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onSubmit = async (e) => {
    e.preventDefault()
    if (!file || submitting) return

    setSubmitting(true)
    try {
      const { job_id } = await uploadDocument(file, form)
      toast.success('Processing started', { title: 'Upload complete' })
      navigate(`/app/job/${job_id}`)
    } catch (err) {
      toast.error(err.message, { title: 'Upload failed' })
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-7">
        <h1 className="font-display text-2xl font-semibold tracking-tight text-fg-strong">
          New teaching package
        </h1>
        <p className="mt-1.5 text-[14px] text-fg-subtle">
          Upload a chapter and answer a couple of questions. Everything else is
          inferred from the document.
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-5">
        <Card>
          <CardBody className="space-y-5">
            <Dropzone
              file={file}
              onFile={setFile}
              onClear={() => setFile(null)}
              extensions={limits.extensions}
              maxSizeMb={limits.maxSizeMb}
              disabled={submitting}
            />

            <Field
              label="What does this document contain?"
              hint="This routes parsing to the cheapest strategy that will work."
            >
              <OptionCards
                name="document_hint"
                value={form.document_hint}
                onChange={set('document_hint')}
                options={DOCUMENT_HINTS}
              />
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardBody className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-3">
              <Field
                label="Output Language"
                hint="Language for materials"
              >
                <Select
                  value={form.language}
                  onChange={set('language')}
                  options={OUTPUT_LANGUAGES.map((l) => ({ value: l.id, label: l.label }))}
                  disabled={submitting}
                />
              </Field>

              <Field
                label="Subject"
                hint="Leave blank to infer from the content"
              >
                <TextInput
                  value={form.subject}
                  onChange={set('subject')}
                  placeholder="e.g. Physics"
                  disabled={submitting}
                />
              </Field>

              <Field label="Grade level">
                <Select
                  value={form.grade}
                  onChange={set('grade')}
                  options={GRADES}
                  disabled={submitting}
                />
              </Field>
            </div>

            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="flex items-center gap-1.5 text-[13px] font-medium text-accent-fg transition-colors hover:text-accent-fg"
            >
              <ChevronDown
                size={14}
                className={`transition-transform ${showAdvanced ? 'rotate-180' : ''}`}
              />
              {showAdvanced ? 'Hide' : 'Show'} teaching preferences
            </button>

            {showAdvanced && (
              <div className="space-y-4 border-t border-default pt-5">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Board / curriculum">
                    <Select
                      value={form.board}
                      onChange={set('board')}
                      options={BOARDS}
                      disabled={submitting}
                    />
                  </Field>

                  <Field label="Teaching style">
                    <Select
                      value={form.teaching_style}
                      onChange={set('teaching_style')}
                      options={TEACHING_STYLES}
                      disabled={submitting}
                    />
                  </Field>

                  <Field
                    label="Minutes per period"
                    hint="Defaults to 40"
                  >
                    <TextInput
                      type="number"
                      min="15"
                      max="180"
                      value={form.period_minutes}
                      onChange={set('period_minutes')}
                      placeholder="40"
                      disabled={submitting}
                    />
                  </Field>

                  <Field
                    label="Periods available"
                    hint="Leave blank to let the content decide"
                  >
                    <TextInput
                      type="number"
                      min="1"
                      max="20"
                      value={form.total_periods_available}
                      onChange={set('total_periods_available')}
                      placeholder="auto"
                      disabled={submitting}
                    />
                  </Field>
                </div>

                <Field label="Assessment depth">
                  <OptionCards
                    name="assessment_depth"
                    value={form.assessment_depth}
                    onChange={set('assessment_depth')}
                    options={ASSESSMENT_DEPTHS}
                    columns={3}
                  />
                </Field>
              </div>
            )}
          </CardBody>
        </Card>

        <div className="flex items-start gap-2.5 rounded-lg border border-default bg-app-subtle px-4 py-3">
          <Info size={15} className="mt-0.5 shrink-0 text-fg-muted" />
          <p className="text-[12.5px] leading-relaxed text-fg-subtle">
            Generation runs ten stages and typically takes one to three minutes.
            You can watch progress live and review each part as it completes.
          </p>
        </div>

        <div className="flex justify-end">
          <Button
            type="submit"
            size="lg"
            disabled={!file}
            loading={submitting}
          >
            {submitting ? 'Starting…' : 'Generate package'}
            {!submitting && <ArrowRight size={16} />}
          </Button>
        </div>
      </form>
    </div>
  )
}
