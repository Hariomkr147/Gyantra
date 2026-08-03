import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { ToastProvider } from '@/components/ui/Toast'
import { AppShell, MarketingShell } from '@/components/layout/AppShell'

const Landing = lazy(() => import('@/pages/Landing'))
const Dashboard = lazy(() => import('@/pages/Dashboard'))
const Upload = lazy(() => import('@/pages/Upload'))
const JobProgress = lazy(() => import('@/pages/JobProgress'))
const Output = lazy(() => import('@/pages/Output'))
const Library = lazy(() => import('@/pages/Library'))

function Spinner() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-strong border-t-[rgb(var(--accent))]" />
    </div>
  )
}

export default function App() {
  return (
    <ToastProvider>
      <BrowserRouter>
        <Suspense fallback={<Spinner />}>
          <Routes>
            {/* Marketing pages — dark theme, single nav bar */}
            <Route element={<MarketingShell />}>
              <Route path="/" element={<Landing />} />
            </Route>

            {/* Workspace — light theme, sidebar */}
            <Route path="/app" element={<AppShell />}>
              <Route index element={<Dashboard />} />
              <Route path="upload" element={<Upload />} />
              <Route path="job/:jobId" element={<JobProgress />} />
              <Route path="output/:jobId" element={<Output />} />
              <Route path="library" element={<Library />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ToastProvider>
  )
}
