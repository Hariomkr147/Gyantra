/**
 * Gyantra API client.
 *
 * All network access goes through this module so error shapes, base URL
 * resolution and the SSE reconnect policy live in exactly one place.
 */

const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export const apiUrl = (path) => `${BASE}${path}`

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(apiUrl(path), options)
  } catch (cause) {
    // Network-level failure: server down, DNS, offline.
    throw new ApiError(
      'Could not reach the Gyantra server. Check that the backend is running.',
      0,
      null,
    )
  }

  const isJson = res.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await res.json().catch(() => null) : null

  if (!res.ok) {
    const detail =
      body?.detail ||
      body?.message ||
      `Request failed with status ${res.status}`
    throw new ApiError(detail, res.status, body)
  }

  return body
}

/* ── endpoints ────────────────────────────────────────────────────────── */

export const getHealth = () => request('/api/health')

export const getConfigOptions = () => request('/api/config/options')

export const listJobs = (limit = 50) => request(`/api/jobs?limit=${limit}`)

export const getJob = (jobId) => request(`/api/jobs/${jobId}`)

export const getPackage = (jobId) => request(`/api/jobs/${jobId}/package`)

export const deleteJob = (jobId) =>
  request(`/api/jobs/${jobId}`, { method: 'DELETE' })

/**
 * Upload a document and start the pipeline.
 * @param {File} file
 * @param {object} opts  document_hint, grade, subject, teaching_style,
 *                       board, language, assessment_depth, period_minutes,
 *                       max_periods, focus
 */
export async function uploadDocument(file, opts = {}) {
  const form = new FormData()
  form.append('file', file)

  for (const [key, value] of Object.entries(opts)) {
    if (value !== undefined && value !== null && value !== '') {
      form.append(key, String(value))
    }
  }

  return request('/api/upload', { method: 'POST', body: form })
}

export const downloadUrl = (jobId, format) =>
  apiUrl(`/api/jobs/${jobId}/download/${format}`)

/**
 * Trigger a browser download without navigating away from the app.
 */
export function triggerDownload(jobId, format) {
  const a = document.createElement('a')
  a.href = downloadUrl(jobId, format)
  a.rel = 'noopener'
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}

/* ── progress streaming ───────────────────────────────────────────────── */

/**
 * Subscribe to a job's progress stream.
 *
 * Uses SSE with an automatic fallback to polling, because free-tier hosting and
 * some corporate proxies buffer or drop event streams. The caller gets the same
 * snapshot shape either way.
 *
 * @returns {() => void} unsubscribe
 */
export function subscribeToProgress(jobId, { onUpdate, onDone, onError } = {}) {
  let closed = false
  let source = null
  let pollTimer = null
  let usedFallback = false

  const finish = (snapshot) => {
    if (closed) return
    closed = true
    cleanup()
    onDone?.(snapshot)
  }

  const cleanup = () => {
    if (source) {
      source.close()
      source = null
    }
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  /* Polling fallback: same contract, lower fidelity. */
  const startPolling = () => {
    if (usedFallback || closed) return
    usedFallback = true
    cleanup()

    const tick = async () => {
      if (closed) return
      try {
        const job = await getJob(jobId)
        onUpdate?.(job)
        if (job.status === 'completed' || job.status === 'failed') {
          finish(job)
          return
        }
      } catch (err) {
        // A 404 means the job is gone; anything else is likely transient.
        if (err.status === 404) {
          closed = true
          onError?.(err)
          return
        }
      }
      pollTimer = setTimeout(tick, 2000)
    }

    tick()
  }

  try {
    source = new EventSource(apiUrl(`/api/jobs/${jobId}/progress`))
  } catch {
    startPolling()
    return () => {
      closed = true
      cleanup()
    }
  }

  source.onmessage = (event) => {
    if (closed) return
    let payload
    try {
      payload = JSON.parse(event.data)
    } catch {
      return
    }

    if (payload.type === 'stream_end') {
      // Fetch the authoritative final job record, which carries the package.
      getJob(jobId)
        .then((job) => finish(job))
        .catch((err) => {
          closed = true
          cleanup()
          onError?.(err)
        })
      return
    }

    if (payload.type === 'error' && payload.message) {
      onError?.(new ApiError(payload.message, 500, payload))
      return
    }

    onUpdate?.(payload)
  }

  source.onerror = () => {
    if (closed) return
    // EventSource retries on its own, but if it never opened we switch to
    // polling rather than leaving the user on a dead progress bar.
    if (source && source.readyState === EventSource.CLOSED) {
      startPolling()
    }
  }

  return () => {
    closed = true
    cleanup()
  }
}
