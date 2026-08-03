import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { AlertCircle, ArrowRight, FileText, RotateCcw } from 'lucide-react'
import { Card, CardBody } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { PipelineStepper, ProgressBar } from '@/components/pipeline/PipelineStepper'
import { useToast } from '@/components/ui/Toast'
import { getJob, subscribeToProgress } from '@/lib/api'
import { STAGE_META, STAGE_ORDER } from '@/lib/constants'
import { formatBytes } from '@/lib/utils'

/** Full stage list up front, so the stepper is complete from the first paint. */
const initialStages = () =>
  STAGE_ORDER.map((stage) => ({
    stage,
    label: STAGE_META[stage].label,
    status: 'pending',
    message: '',
  }))

/**
 * Turn a backend error into something a teacher can act on.
 * The raw message is kept — hiding it makes debugging impossible — but a
 * plain-language hint is added for the failures that have an obvious fix.
 */
function explainError(raw, stage) {
  const text = String(raw || '')
  const lower = text.toLowerCase()

  if (lower.includes('no llm provider')) {
    return {
      title: 'No AI provider configured',
      hint: 'Add GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY to backend/.env and restart the server. Set DEMO_MODE=true to try the app without a key.',
    }
  }
  if (lower.includes('all providers failed')) {
    return {
      title: 'Every AI provider failed',
      hint: 'The configured providers were unreachable, rate-limited, or returned errors. Check the backend log for the per-attempt detail, then retry.',
    }
  }
  if (lower.includes('rate limit') || lower.includes('429')) {
    return {
      title: 'Provider rate limit reached',
      hint: 'Your free-tier quota is exhausted. Wait for it to reset, add a second provider key as fallback, or switch to a paid tier.',
    }
  }
  if (lower.includes('no readable text')) {
    return {
      title: 'Could not read the document',
      hint: 'No extractable text was found. If this is a scanned PDF, install tesseract and set OCR_ENABLED=true, then re-upload.',
    }
  }
  if (lower.includes('no concepts')) {
    return {
      title: 'No teachable concepts found',
      hint: 'The document parsed, but no educational concepts could be extracted. It may not be instructional content.',
    }
  }
  if (lower.includes('timed out') || lower.includes('timeout')) {
    return {
      title: 'Generation timed out',
      hint: 'The job exceeded its time limit. A shorter document, or a faster model, should complete.',
    }
  }

  return {
    title: stage
      ? `Failed during ${STAGE_META[stage]?.label || stage}`
      : 'Generation failed',
    hint: '',
  }
}

export default function JobProgress() {
  const { jobId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()

  const [job, setJob] = useState(null)
  const [stages, setStages] = useState(initialStages)
  const [progress, setProgress] = useState(0)
  const [status, setStatus] = useState('queued')
  const [error, setError] = useState('')
  const [failedStage, setFailedStage] = useState(null)
  const [degraded, setDegraded] = useState([])
  const [loading, setLoading] = useState(true)

  // Stops a late SSE event from overwriting a terminal state.
  const settled = useRef(false)

  const patchStage = useCallback((stageId, patch) => {
    setStages((list) =>
      list.map((s) => (s.stage === stageId ? { ...s, ...patch } : s)),
    )
  }, [])

  const applySnapshot = useCallback((snapshot) => {
    if (Array.isArray(snapshot.stages) && snapshot.stages.length) {
      setStages(
        STAGE_ORDER.map((id) => {
          const found = snapshot.stages.find((s) => s.stage === id)
          return (
            found || {
              stage: id,
              label: STAGE_META[id].label,
              status: 'pending',
              message: '',
            }
          )
        }),
      )
      const failed = snapshot.stages.find((s) => s.status === 'failed')
      if (failed) setFailedStage(failed.stage)
    }
    if (typeof snapshot.progress === 'number') setProgress(snapshot.progress)
    if (snapshot.status) setStatus(snapshot.status)
    if (snapshot.error || snapshot.error_message) {
      setError(snapshot.error || snapshot.error_message)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    settled.current = false

    getJob(jobId)
      .then((data) => {
        if (cancelled) return
        setJob(data)
        applySnapshot(data)
        setLoading(false)
        if (data.status === 'completed') {
          settled.current = true
          navigate(`/app/output/${jobId}`, { replace: true })
        }
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message)
        setStatus('failed')
        setLoading(false)
      })

    const unsubscribe = subscribeToProgress(jobId, {
      onUpdate: (event) => {
        if (cancelled || settled.current) return

        if (event.type === 'snapshot' || event.stages) {
          applySnapshot(event)
          return
        }
        if (typeof event.progress === 'number') setProgress(event.progress)

        switch (event.type) {
          case 'job_started':
            setStatus('running')
            break
          case 'stage_started':
            setStatus('running')
            patchStage(event.stage, {
              status: 'running',
              message: event.message || '',
            })
            break
          case 'stage_progress':
            patchStage(event.stage, { message: event.message || '' })
            break
          case 'stage_completed':
            patchStage(event.stage, {
              status: 'completed',
              message: event.message || '',
            })
            break
          case 'stage_failed':
            patchStage(event.stage, {
              status: 'failed',
              message: event.error || 'Stage failed',
            })
            if (event.fatal === false) {
              // Non-critical: the run continues with a partial package.
              const label = STAGE_META[event.stage]?.label || event.stage
              setDegraded((list) => [...list, label])
              toast.warning(
                `${label} could not complete. The package will be missing that section.`,
              )
            } else {
              setFailedStage(event.stage)
            }
            break
          case 'job_failed':
            setStatus('failed')
            setError(event.error || 'The pipeline failed.')
            if (event.stage) setFailedStage(event.stage)
            break
          default:
            break
        }
      },

      onDone: (finalJob) => {
        if (cancelled) return
        settled.current = true

        if (finalJob?.status === 'completed') {
          setStatus('completed')
          setProgress(100)
          applySnapshot(finalJob)
          navigate(`/app/output/${jobId}`, { replace: true })
        } else if (finalJob) {
          setStatus(finalJob.status)
          applySnapshot(finalJob)
          if (finalJob.error_message) setError(finalJob.error_message)
        }
      },

      onError: (err) => {
        if (cancelled || settled.current) return
        setError(err.message)
      },
    })

    return () => {
      cancelled = true
      unsubscribe()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])

  const running = status === 'running' || status === 'queued'
  const failed = status === 'failed'

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl space-y-5">
        <div className="skeleton h-8 w-64" />
        <Card>
          <CardBody className="space-y-6">
            <div className="skeleton h-1.5 w-full rounded-full" />
            <PipelineStepper stages={[]} />
          </CardBody>
        </Card>
      </div>
    )
  }

  const explained = failed ? explainError(error, failedStage) : null

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="font-display text-[26px] font-semibold tracking-tight text-fg-strong">
              {failed
                ? 'Generation failed'
                : running
                  ? 'Building your package'
                  : 'Package ready'}
            </h1>
            {job && (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[13px] text-fg-muted">
                <FileText size={14} aria-hidden="true" />
                <span className="truncate font-medium">{job.file_name}</span>
                {job.file_size_bytes > 0 && (
                  <>
                    <span aria-hidden="true">·</span>
                    <span>{formatBytes(job.file_size_bytes)}</span>
                  </>
                )}
              </div>
            )}
          </div>
          {running && (
            <Badge tone="accent">
              <span className="tabular-nums">{progress}%</span>
            </Badge>
          )}
        </div>
      </header>

      {failed && (
        <Card className="mb-5 border-l-[3px] border-l-[rgb(var(--danger-fg))]">
          <CardBody className="flex items-start gap-3.5">
            <AlertCircle
              size={19}
              className="mt-0.5 shrink-0 text-danger"
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <h2 className="text-[15px] font-semibold text-fg-strong">
                {explained.title}
              </h2>
              {explained.hint && (
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-fg-muted">
                  {explained.hint}
                </p>
              )}
              {error && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-[12.5px] font-medium text-fg-muted hover:text-fg">
                    Technical detail
                  </summary>
                  <pre className="code-block mt-2 max-h-52 overflow-auto whitespace-pre-wrap p-3">
                    {error}
                  </pre>
                </details>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                <Link to="/app/upload">
                  <Button size="sm">
                    <RotateCcw size={14} />
                    Try another document
                  </Button>
                </Link>
                <Link to="/app/library">
                  <Button variant="secondary" size="sm">
                    Back to library
                  </Button>
                </Link>
              </div>
            </div>
          </CardBody>
        </Card>
      )}

      {degraded.length > 0 && !failed && (
        <Card className="mb-5 border-l-[3px] border-l-[rgb(var(--warn-fg))]">
          <CardBody className="flex items-start gap-3">
            <AlertCircle
              size={17}
              className="mt-0.5 shrink-0 text-warn"
              aria-hidden="true"
            />
            <p className="text-[13.5px] leading-relaxed text-fg-muted">
              <span className="font-medium text-fg">
                Some stages could not complete:
              </span>{' '}
              {degraded.join(', ')}. The rest of the package was still generated.
            </p>
          </CardBody>
        </Card>
      )}

      <Card>
        <CardBody className="space-y-6">
          <div>
            <div className="mb-2 flex items-center justify-between text-[12.5px]">
              <span className="font-medium text-fg">
                {running ? 'Processing' : failed ? 'Stopped' : 'Complete'}
              </span>
              <span className="font-mono tabular-nums text-fg-muted">
                {progress}%
              </span>
            </div>
            <ProgressBar value={progress} active={running} />
          </div>

          <PipelineStepper stages={stages} />
        </CardBody>
      </Card>

      {status === 'completed' && (
        <div className="mt-5 flex justify-end">
          <Link to={`/app/output/${jobId}`}>
            <Button>
              View package
              <ArrowRight size={16} />
            </Button>
          </Link>
        </div>
      )}

      {running && (
        <p className="mt-5 text-center text-[12.5px] text-fg-subtle">
          You can leave this page. Generation continues in the background and the
          result appears in your library.
        </p>
      )}
    </div>
  )
}
