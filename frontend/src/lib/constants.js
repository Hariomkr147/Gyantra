/**
 * Display metadata for pipeline stages and enums.
 *
 * The backend is the source of truth for stage *identity* (via
 * /api/config/options); this file only holds presentation details the API has
 * no reason to know about.
 */

export const STAGE_META = {
  document_intelligence: {
    label: 'Document Intelligence',
    blurb: 'Parsing structure, tables, figures and equations',
  },
  classification: {
    label: 'Educational Classification',
    blurb: 'Inferring subject, grade, topic and difficulty',
  },
  knowledge_extraction: {
    label: 'Knowledge Extraction',
    blurb: 'Building the concept map, objectives and definitions',
  },
  teaching_plan: {
    label: 'Teaching Planner',
    blurb: 'Sequencing content into an adaptive period plan',
  },
  classroom_content: {
    label: 'Classroom Content',
    blurb: 'Writing scripts, board notes and checkpoints',
  },
  activities: {
    label: 'Activity Generation',
    blurb: 'Designing demonstrations, discussions and tasks',
  },
  assessments: {
    label: 'Assessment Generation',
    blurb: 'Creating questions, answer keys and rubrics',
  },
  gap_analysis: {
    label: 'Learning Gap Analysis',
    blurb: 'Diagnosing likely misconceptions and remedies',
  },
  validation: {
    label: 'Validation',
    blurb: 'Checking schema, consistency and grounding',
  },
  publishing: {
    label: 'Publishing',
    blurb: 'Packaging JSON and printable PDFs',
  },
}

export const STAGE_ORDER = Object.keys(STAGE_META)

export const DOCUMENT_HINTS = [
  {
    value: 'mostly_text',
    label: 'Mostly text',
    hint: 'Prose chapters. Fastest and cheapest to parse.',
  },
  {
    value: 'text_with_tables',
    label: 'Text with tables',
    hint: 'Preserves tabular data structure.',
  },
  {
    value: 'text_with_diagrams',
    label: 'Text with diagrams',
    hint: 'Keeps figure references and captions.',
  },
  {
    value: 'text_with_equations',
    label: 'Text with equations',
    hint: 'Keeps formulas tied to their concepts.',
  },
  {
    value: 'scanned_pdf',
    label: 'Scanned PDF',
    hint: 'Runs OCR. Slower, for image-only pages.',
  },
  {
    value: 'not_sure',
    label: 'Let the system decide',
    hint: 'Gyantra inspects the file and picks a strategy.',
  },
]

export const TEACHING_STYLES = [
  { value: '', label: 'No preference' },
  { value: 'conceptual', label: 'Conceptual understanding' },
  { value: 'exam_oriented', label: 'Exam oriented' },
  { value: 'activity_based', label: 'Activity based' },
  { value: 'balanced', label: 'Balanced' },
]

export const ASSESSMENT_DEPTHS = [
  { value: 'light', label: 'Light' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'thorough', label: 'Thorough' },
]

export const SEVERITY_STYLES = {
  high: 'bg-red-500/12 text-red-300 border-red-500/25',
  medium: 'bg-amber-500/12 text-amber-300 border-amber-500/25',
  low: 'bg-sky-500/12 text-sky-300 border-sky-500/25',
}

export const VALIDATION_STYLES = {
  pass: 'bg-emerald-500/12 text-emerald-300 border-emerald-500/25',
  warn: 'bg-amber-500/12 text-amber-300 border-amber-500/25',
  fail: 'bg-red-500/12 text-red-300 border-red-500/25',
}

export const ACTIVITY_LABELS = {
  discussion: 'Discussion',
  demonstration: 'Demonstration',
  experiment: 'Experiment',
  role_play: 'Role play',
  worksheet: 'Worksheet',
  group_task: 'Group task',
  board_work: 'Board work',
  think_pair_share: 'Think-pair-share',
  case_study: 'Case study',
}

export const BLOOM_ORDER = [
  'remember',
  'understand',
  'apply',
  'analyze',
  'evaluate',
  'create',
]

export const DOWNLOAD_FORMATS = [
  {
    id: 'json',
    label: 'TeacherKnowledgePackage.json',
    hint: 'Canonical structured output',
  },
  { id: 'lesson-plan', label: 'Lesson Plan PDF', hint: 'Period-by-period plan' },
  {
    id: 'teacher-guide',
    label: 'Teacher Guide PDF',
    hint: 'Concepts, activities, gap analysis',
  },
  {
    id: 'assessments',
    label: 'Assessment Pack PDF',
    hint: 'Questions with answer key',
  },
]

export const OUTPUT_LANGUAGES = [
  { id: 'en', label: 'English' },
  { id: 'hi', label: 'हिन्दी (Hindi)' },
  { id: 'bn', label: 'বাংলা (Bengali)' },
  { id: 'ta', label: 'தமிழ் (Tamil)' },
  { id: 'te', label: 'తెలుగు (Telugu)' },
  { id: 'mr', label: 'मराठी (Marathi)' },
]
