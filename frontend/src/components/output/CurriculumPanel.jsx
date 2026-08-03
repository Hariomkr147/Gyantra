import { Card, CardBody, EmptyState } from '@/components/ui/Card'
import { BookOpen, GraduationCap, Link2 } from 'lucide-react'

export function CurriculumPanel({ alignment }) {
  if (!alignment) {
    return (
      <EmptyState
        icon={BookOpen}
        title="No curriculum alignment"
        description="Curriculum alignment was not generated for this package."
      />
    )
  }

  const { target_standard, mapped_standards, coverage_score } = alignment

  return (
    <div className="space-y-4">
      <Card>
        <CardBody className="flex flex-col gap-2">
          <div className="flex items-center gap-2 mb-2">
            <GraduationCap size={20} className="text-accent-fg" />
            <h3 className="text-[15px] font-semibold text-fg-strong">
              Target Standard: {target_standard || 'Unknown'}
            </h3>
          </div>
          <p className="text-[13px] text-fg-muted">
            Coverage Score: {coverage_score ? `${(coverage_score * 100).toFixed(0)}%` : 'N/A'}
          </p>
        </CardBody>
      </Card>

      {mapped_standards && mapped_standards.length > 0 && (
        <Card>
          <CardBody>
            <h4 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-fg-muted">
              Aligned Standards
            </h4>
            <div className="space-y-4">
              {mapped_standards.map((std, i) => (
                <div key={i} className="flex gap-3 text-[13px] leading-relaxed text-fg-muted">
                  <Link2 size={16} className="mt-0.5 shrink-0 text-app-subtle" />
                  <div>
                    <div className="font-semibold text-fg-strong">{std.standard_code}</div>
                    <div className="mt-1">{std.description}</div>
                    {std.matching_concepts && std.matching_concepts.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {std.matching_concepts.map((conceptId) => (
                          <span key={conceptId} className="inline-flex items-center rounded-md bg-app-subtle px-1.5 py-0.5 text-[11px] font-medium text-fg-subtle">
                            {conceptId}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  )
}
