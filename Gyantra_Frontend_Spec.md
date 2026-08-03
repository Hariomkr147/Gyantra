# Gyantra Frontend Specification

**Purpose:** This document describes the frontend for **Gyantra**, an AI platform that transforms educational documents into a classroom-ready Teacher Knowledge Package (TKP). It is written as a build spec for an LLM agent or frontend developer.

**Reference inspiration from the uploaded PDF:**  
The uploaded website breakdown emphasizes a polished, motion-led landing page built with a small stack of proven tools: **GSAP + ScrollTrigger** for animation, **Lenis** for smooth scrolling, selective use of 3D only when truly needed, a **single accent color**, cinematic intro loaders, and strong mobile performance discipline. Those ideas should inform the Gyantra frontend, but the app itself should remain a productivity tool rather than an Awwwards-style portfolio site.

---

## 1. Product Vision

Gyantra should feel like a modern AI workspace for teachers, not a generic upload form. The frontend must make three ideas obvious immediately:

1. **Upload any educational document.**
2. **Watch the system convert it into structured pedagogy.**
3. **Review and export a teacher-ready package.**

The interface should communicate:
- trust
- clarity
- speed
- academic seriousness
- premium AI-assisted workflow

The user should always know:
- what document is being processed
- which stage the pipeline is on
- what is generated so far
- how to export or reuse the output

---

## 2. Frontend Principles

### 2.1 What the frontend should feel like
- Calm and confident, not playful.
- AI-assisted, but teacher-first.
- Clean and spacious, with restrained animation.
- High-end product feel, but not visually noisy.
- Strong hierarchy: the upload action, processing state, and generated outputs should be impossible to miss.

### 2.2 What to avoid
- Overly decorative 3D scenes.
- Heavy scroll gimmicks that slow down the app.
- Too many accent colors.
- Dense dashboards with no spacing.
- Long transitions that make the app feel slow.
- Visuals that look like a generic SaaS template.

### 2.3 Motion guidance derived from the PDF
Use the motion ideas from the PDF in a restrained way:
- **Lenis** for smooth scrolling on the landing page only.
- **GSAP** for hero text reveals, section transitions, card stagger animations, and pipeline progress bars.
- A short **cinematic loader** for first impression, but keep it under 2.5 seconds.
- Use scroll storytelling only on the marketing/landing page.
- Do not use heavy 3D unless there is a very specific hero effect requirement.
- Use one primary accent color consistently across buttons, active states, highlights, and progress indicators.

---

## 3. Recommended Tech Stack

The frontend should be built with:

- **Next.js** or **React + Vite** for app structure
- **Tailwind CSS** for layout and styling
- **shadcn/ui** for accessible component primitives
- **Framer Motion** for small component-level interactions
- **GSAP + ScrollTrigger** for landing page motion
- **Lenis** for smooth scroll on marketing pages
- **Lucide Icons** for iconography
- **React Hook Form** for form handling
- **Zod** for client-side validation
- **TanStack Query** or equivalent for API state
- **Monaco Editor** or a lightweight code-style viewer only if JSON preview requires a structured editor feel

Optional:
- **Lottie** for subtle AI/loading illustrations
- **Recharts** or **ECharts** for analytics and review dashboards

---

## 4. Information Architecture

Gyantra should be divided into two broad experiences:

### 4.1 Public / Marketing Experience
This is the first impression for visitors.

Routes:
- `/` → Landing page
- `/demo` → Demo walkthrough or sample upload flow
- `/about` → Optional project explanation
- `/pricing` → Not required unless you want to show an optional model-cost story
- `/login` → Auth entry
- `/signup` → Auth entry

### 4.2 Authenticated App Experience
This is the teacher workspace.

Routes:
- `/app` → Main dashboard
- `/app/upload` → Document upload flow
- `/app/job/[id]` → Pipeline execution and progress
- `/app/output/[id]` → Generated TKP viewer
- `/app/output/[id]/lesson-plan` → Period-wise teaching plan
- `/app/output/[id]/assessments` → Assessment package
- `/app/output/[id]/activities` → Activity package
- `/app/library` → Saved outputs and history
- `/app/settings` → User preferences, API settings, model choice
- `/app/admin` → Optional system monitoring page if needed

---

## 5. Overall Layout Strategy

### 5.1 Landing page layout
The landing page should be vertically structured and scroll-driven:

1. Hero section
2. How it works
3. Core pipeline
4. Key features
5. Output preview
6. Why it is grounded
7. Demo / CTA
8. Footer

Use scroll reveal for each section. The content should flow like a product story:
- document in
- structure extracted
- lesson plan generated
- classroom package exported

### 5.2 App layout
The authenticated workspace should use a more practical pattern:
- left sidebar navigation
- top utility bar
- main content area
- contextual right panel only when needed

The app layout should prioritize:
- upload state visibility
- job progress
- output preview
- editing/review actions
- export actions

---

## 6. Visual Design System

### 6.1 Color system
Use a single dominant accent color inspired by the reference PDF’s advice on consistency.

Suggested palette:
- **Background:** deep navy / slate
- **Surface:** dark charcoal or soft off-white depending on theme
- **Primary accent:** teal
- **Secondary accent:** lighter teal/cyan used sparingly
- **Text:** strong near-black on light mode, off-white on dark mode
- **Borders:** subtle, low-contrast neutral lines

Recommended style:
- Dark-first marketing site
- Light or neutral workspace
- Avoid rainbow gradients
- Use accent color for buttons, active tabs, progress bars, and focus states only

### 6.2 Typography
Use a modern sans serif with strong readability.

Suggested pairing:
- **Headings:** Inter, Sora, or Manrope
- **Body:** Inter or system sans
- **Code / JSON preview:** JetBrains Mono or similar monospace font

Typography rules:
- Large, confident hero headlines
- Clear section titles
- Comfortable line height in text-heavy areas
- Numbers and status labels should be easy to scan

### 6.3 Spacing and layout
- Use generous whitespace.
- Keep a strong 12-column layout on desktop.
- Use card grids for features and outputs.
- Keep content width constrained for readability.
- Use consistent vertical rhythm between sections.

### 6.4 Shadows and surfaces
- Use soft shadows, not heavy drop shadows.
- Prefer layered cards with subtle elevation.
- Use border + slight background variation instead of flashy depth.

---

## 7. Core Frontend Components

Build these reusable components first:

### 7.1 Navigation
- `Navbar`
- `Sidebar`
- `MobileDrawer`
- `Breadcrumbs`

### 7.2 Action components
- `PrimaryButton`
- `SecondaryButton`
- `GhostButton`
- `IconButton`
- `UploadDropzone`

### 7.3 Status components
- `PipelineStepper`
- `JobProgressBar`
- `StatusBadge`
- `StageTimeline`
- `ValidationPill`
- `GroundingBadge`

### 7.4 Display components
- `FeatureCard`
- `LessonPeriodCard`
- `ActivityCard`
- `AssessmentCard`
- `OutputPreviewPanel`
- `JsonTreeViewer`
- `MetadataSummaryCard`
- `SourceCitationPanel`

### 7.5 Feedback components
- `Toast`
- `Alert`
- `EmptyState`
- `Skeleton`
- `LoadingOverlay`
- `ErrorState`

### 7.6 Data visualization components
- `ConceptCoverageChart`
- `LessonSequenceTimeline`
- `ConfidenceMeter`
- `ValidationCheckList`
- `MisconceptionPanel`

---

## 8. Landing Page Specification

The landing page should be cinematic, but still minimal and trustworthy.

### 8.1 Hero section
Purpose:
- Explain the product in one glance.

Layout:
- Top navigation with logo and sign-in button
- Large headline
- Short supporting paragraph
- Primary CTA: “Upload a Chapter”
- Secondary CTA: “See Demo”
- A visual panel showing the pipeline or generated package

Visual ideas:
- subtle animated gradient background
- moving lines or soft particles
- floating document cards
- an AI-style workflow panel

Motion:
- headline fades in line by line
- supporting text slides upward slightly
- CTA buttons appear with slight stagger
- visual panel animates after the text

Do not make the hero cluttered.

### 8.2 How it works section
Show the end-to-end workflow in 4 or 5 steps:
1. Upload document
2. Extract structure
3. Classify and understand content
4. Generate teaching package
5. Validate and export

Each step should have:
- icon
- short title
- one-line explanation
- micro animation on scroll

### 8.3 Core pipeline section
This section should explain the AI architecture in a human-friendly way.

Suggested stages:
- Document Intelligence
- Educational Classification
- Knowledge Extraction
- Teaching Planning
- Classroom Content Generation
- Activity & Assessment Generation
- Validation
- Publishing

The frontend should present these as connected cards or a vertical pipeline timeline.

### 8.4 Output preview section
Show what the teacher receives:
- structured lesson plan
- activities
- assessment set
- misconception analysis
- TeacherKnowledgePackage.json
- downloadable PDF outputs

The preview should look credible and useful, not promotional.

### 8.5 Trust and grounding section
Very important for this project.

Communicate that:
- outputs are grounded in the source document
- citations or source references are preserved where possible
- validation checks reduce hallucinations
- external pedagogical help is allowed only when clearly separated from source facts

This section should feel like a trust guarantee.

### 8.6 Final CTA section
End with:
- “Upload your chapter”
- “Generate a classroom-ready package”
- minimal form or button

---

## 9. Upload Flow Specification

This is the most important product workflow.

### 9.1 Upload screen layout
The upload page should have:
- clear title
- brief instruction text
- drag-and-drop upload area
- supported file types
- document classification options
- primary CTA

### 9.2 Upload metadata fields
Allow the user to provide:
- subject
- grade
- language
- board/curriculum
- teaching objective
- time constraints
- document type
- complexity preference

If the user is not sure, the UI should support:
- “Let the system decide”

### 9.3 Smart routing
Based on the PDF analysis, the frontend should encourage cost-aware routing.

Show a simple selector:
- Mostly text
- Text with tables
- Text with diagrams/figures
- Text with equations
- Scanned PDF
- Not sure

This is not just a design detail; it helps the backend choose the right parsing strategy.

### 9.4 Upload states
The upload flow should handle:
- idle
- file selected
- upload in progress
- upload complete
- upload error
- retry

Provide a clear file summary after selection:
- filename
- type
- size
- pages detected
- estimated processing mode

---

## 10. Job Progress and Pipeline UI

The pipeline screen is central to the product experience.

### 10.1 Progress layout
Use a stepper or vertical timeline showing:
- Document parsing
- Classification
- Knowledge extraction
- Planning
- Lesson generation
- Activity generation
- Assessment generation
- Validation
- Export

### 10.2 What the user should see
For each stage:
- stage name
- short description
- percentage progress
- success/failure state
- log messages or summary notes

### 10.3 Live update behavior
- The UI should support streaming updates.
- Completed stages should visually lock in.
- Current stage should be highlighted.
- Failed stages should show an actionable error message.
- The user should be able to continue reviewing earlier stages while the next stage runs.

### 10.4 Microinteractions
- Progress bars animate smoothly.
- Stage completion should trigger a subtle checkmark.
- Loading states should never feel frozen.
- Use optimistic UI when safe.

---

## 11. Output Viewer Specification

This is where the generated TKP is reviewed.

### 11.1 Main structure
The output page should be split into tabs or sections:

- Overview
- Lesson Plan
- Content by Period
- Activities
- Assessments
- Gap Analysis
- Source Traceability
- JSON Preview
- Export

### 11.2 Overview panel
Show:
- title of the generated package
- subject
- grade
- topic
- number of periods
- language
- confidence / validation summary

### 11.3 Lesson plan view
Each period should be displayed as a card with:
- learning objectives
- concept flow
- teacher script summary
- board notes
- activity
- exit ticket
- homework

### 11.4 Assessments view
Show:
- MCQs
- short answers
- long answers
- answer key
- rubric

Prefer accordion cards so the page stays manageable.

### 11.5 Gap analysis view
Show:
- misconception name
- why it matters
- severity
- diagnostic question
- remediation strategy

### 11.6 JSON preview
Provide a collapsible or syntax-highlighted JSON view.

Features:
- pretty print
- copy button
- download button
- search within JSON
- optional tree view for nested data

### 11.7 Export actions
Include export controls for:
- download JSON
- download PDF lesson book
- copy share link
- export selected sections only

---

## 12. Design for Validation and Grounding

This project must feel trustworthy.

### 12.1 Validation UI
Show a validation summary with:
- schema check passed/failed
- grounding check status
- missing sections
- consistency warnings
- citation/source coverage

### 12.2 Source traceability
Where possible, the frontend should let the user see:
- which source section produced which output
- which concepts were extracted from which pages
- which content was added as pedagogical support rather than source fact

### 12.3 Warning patterns
If something looks uncertain:
- highlight it
- explain the issue in plain language
- offer a regenerate button or manual review option

---

## 13. Responsive Behavior

### 13.1 Mobile
On mobile, prioritize:
- upload
- job progress
- key lesson output
- export

Use:
- stacked cards
- collapsible sections
- sticky action bar
- simpler navigation

### 13.2 Tablet
Tablet should show:
- split-pane output viewer
- narrower sidebar
- multi-column cards where appropriate

### 13.3 Desktop
Desktop can show:
- sidebar + content + details panel
- richer previews
- larger JSON viewer
- multi-tab review mode

---

## 14. Accessibility Requirements

The frontend should be usable and readable.

Must support:
- keyboard navigation
- visible focus states
- sufficient color contrast
- semantic headings
- descriptive button labels
- screen-reader-friendly progress updates
- no color-only status meaning
- reduced motion mode

For motion-heavy components:
- respect `prefers-reduced-motion`
- replace animation with instant transitions when needed

---

## 15. Empty States and Error States

These are important for a polished UX.

### 15.1 Empty states
Examples:
- no documents uploaded yet
- no generated output yet
- no saved history
- no validations run yet

Each empty state should:
- explain the state
- tell the user what to do next
- include a primary action button

### 15.2 Error states
Handle:
- unsupported file type
- file too large
- parsing failed
- AI generation failed
- validation failed
- network timeout
- export failure

Every error should include:
- a human-readable message
- a retry action
- a fallback path if possible

---

## 16. Motion and Animation Rules

This is where the PDF’s advice should be applied carefully.

### Use motion for:
- hero reveal
- section entrance
- progress updates
- tab transitions
- card hover states
- subtle loaders

### Avoid motion for:
- long forms
- dense tables
- critical review screens
- anything that reduces readability

### Timing rules
- Micro-interactions: fast
- Section reveal: moderate
- Full page transitions: restrained
- Loader: short and purposeful

### Animation style
- smooth
- minimal
- premium
- never distracting

---

## 17. Component Priorities for the First Build

If implementing in phases, build in this order:

1. Landing page
2. Upload flow
3. Job progress screen
4. Output viewer
5. JSON preview
6. Validation panel
7. Export actions
8. History/library
9. Settings
10. Optional admin/monitoring tools

---

## 18. Suggested Folder Structure

```text
src/
  app/
    page.tsx
    layout.tsx
    login/
    signup/
    dashboard/
    upload/
    job/[id]/
    output/[id]/
    library/
    settings/
  components/
    ui/
    layout/
    upload/
    pipeline/
    output/
    charts/
    motion/
  lib/
    api/
    hooks/
    utils/
    validation/
    constants/
  styles/
  assets/
```

---

## 19. Content Style and Tone

### UI copy should be:
- calm
- teacher-friendly
- precise
- non-technical when possible
- reassuring

### Examples of good copy
- “Upload a chapter to generate a classroom-ready package.”
- “Processing document structure.”
- “Validation passed.”
- “Grounded in source content.”
- “Export lesson plan.”

### Avoid copy like
- “AI magic”
- “Revolutionary”
- “Unleash productivity”
- “Next-gen education disruption”

---

## 20. Frontend Deliverable Standard

The frontend should be considered complete when:

- the landing page clearly explains Gyantra
- the upload flow is intuitive
- the progress pipeline is visible and trustworthy
- generated outputs can be reviewed section by section
- JSON and PDF exports are available
- the UI looks polished on mobile and desktop
- the design feels consistent across the whole app
- motion improves clarity rather than becoming decoration

---

## 21. Final Build Direction

The best visual direction for Gyantra is:

**“A premium teacher workspace with a cinematic landing page.”**

That means:
- polished marketing front
- functional dashboard back
- one accent color
- restrained animation
- strong trust signals
- fast, readable, useful product UX

The frontend should not try to be a flashy portfolio. It should feel like a serious AI education product that can actually help a teacher go from raw document to lesson plan quickly and confidently.
