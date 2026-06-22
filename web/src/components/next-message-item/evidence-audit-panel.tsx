import { IEvidenceAudit } from '@/interfaces/database/chat';
import { cn } from '@/lib/utils';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileText,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

type IProps = {
  audit?: IEvidenceAudit;
};

const evidenceTypeClass: Record<string, string> = {
  original_text: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  raptor_summary_with_sources: 'border-amber-200 bg-amber-50 text-amber-800',
  raptor_summary: 'border-amber-200 bg-amber-50 text-amber-800',
  title_only: 'border-slate-200 bg-slate-50 text-slate-700',
  weak_context: 'border-slate-200 bg-slate-50 text-slate-700',
};

const formatFig = (figId?: number) =>
  typeof figId === 'number' && Number.isFinite(figId) ? `Fig.${figId + 1}` : '';

export function EvidenceAuditPanel({ audit }: IProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const citedEvidence = useMemo(
    () => (audit?.evidence ?? []).filter((item) => item.is_cited),
    [audit?.evidence],
  );
  const visibleEvidence = citedEvidence.length
    ? citedEvidence
    : (audit?.evidence ?? []).slice(0, 4);

  if (!audit || !audit.retrieval) {
    return null;
  }

  const retrieval = audit.retrieval;
  const warnings = audit.warnings ?? [];
  const candidateChunks = retrieval.candidate_chunks ?? 0;
  const candidateDocs = retrieval.candidate_docs ?? 0;
  const selectedChunks = retrieval.selected_chunks ?? 0;
  const hasEvidenceDetails =
    (audit.evidence ?? []).length > 0 ||
    (audit.answer_basis ?? []).length > 0 ||
    (audit.answer_evidence_plan ?? []).length > 0 ||
    warnings.length > 0;

  if (
    candidateChunks === 0 &&
    candidateDocs === 0 &&
    selectedChunks === 0 &&
    !hasEvidenceDetails
  ) {
    return null;
  }

  return (
    <section className="mt-2 w-full max-w-3xl rounded-md border border-[#d9c7cf] bg-white/72 p-3 text-sm text-slate-700 shadow-sm dark:border-[#38546a] dark:bg-[#142637]/72 dark:text-slate-100">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 text-left"
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="inline-flex items-center gap-2 font-semibold text-[#5b2737] dark:text-[#d7e7f0]">
          <FileText className="size-4" />
          {t('chat.evidenceAudit')}
        </span>
        <span className="inline-flex items-center gap-3 text-xs text-slate-500 dark:text-slate-300">
          {t('chat.evidenceAuditStats', {
            chunks: candidateChunks,
            docs: candidateDocs,
            selected: selectedChunks,
          })}
          {expanded ? (
            <ChevronUp className="size-4" />
          ) : (
            <ChevronDown className="size-4" />
          )}
        </span>
      </button>

      {expanded && (
        <div className="mt-3 space-y-3">
          {audit.rewritten_query && (
            <div className="rounded bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600 dark:bg-[#0d1d2a] dark:text-slate-300">
              <span className="font-medium">
                {t('chat.evidenceAuditQuery')}:
              </span>{' '}
              {audit.rewritten_query}
            </div>
          )}

          {warnings.length > 0 && (
            <div className="space-y-1">
              {warnings.slice(0, 3).map((warning, index) => (
                <div
                  key={`${index}-${warning}`}
                  className="flex gap-2 rounded bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
                >
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                  <span>{warning}</span>
                </div>
              ))}
            </div>
          )}

          <div className="grid gap-2">
            {visibleEvidence.map((item) => (
              <article
                key={`${item.id}-${item.chunk_id}`}
                className={cn(
                  'rounded border p-2',
                  evidenceTypeClass[item.type] ??
                    'border-slate-200 bg-slate-50 text-slate-700',
                )}
              >
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {item.is_cited && <CheckCircle2 className="size-3.5" />}
                  {item.is_cited && formatFig(item.fig_id) && (
                    <span className="font-semibold">
                      {formatFig(item.fig_id)}
                    </span>
                  )}
                  <span className="font-semibold">
                    {item.is_cited && formatFig(item.fig_id)
                      ? `${t('chat.evidenceAuditSourceId')}:${item.id}`
                      : `ID:${item.id}`}
                  </span>
                  <span>{item.type}</span>
                  {typeof item.score === 'number' && (
                    <span>score {item.score}</span>
                  )}
                  {item.has_image && <span>Fig</span>}
                </div>
                {item.doc_name && (
                  <div className="mt-1 truncate text-xs font-medium">
                    {item.doc_name}
                  </div>
                )}
                {item.why && (
                  <div className="mt-1 text-xs leading-5">{item.why}</div>
                )}
                {item.preview && (
                  <div className="mt-1 line-clamp-2 text-xs leading-5 opacity-85">
                    {item.preview}
                  </div>
                )}
              </article>
            ))}
          </div>

          {(audit.answer_basis ?? []).length > 0 && (
            <div className="rounded bg-slate-50 px-3 py-2 text-xs leading-5 dark:bg-[#0d1d2a]">
              <div className="mb-1 font-semibold">
                {t('chat.evidenceAuditBasis')}
              </div>
              {(audit.answer_basis ?? []).map((basis, index) => (
                <div key={`${index}-${basis.claim}`}>
                  {basis.claim}:{' '}
                  {(basis.source_ids ?? [])
                    .map((id, sourceIndex) => {
                      const figId = basis.fig_ids?.[sourceIndex];
                      const figLabel = formatFig(figId);
                      return figLabel
                        ? `${figLabel}(${t('chat.evidenceAuditSourceId')}:${id})`
                        : `ID:${id}`;
                    })
                    .join(', ')}
                </div>
              ))}
            </div>
          )}

          {(audit.answer_evidence_plan ?? []).length > 0 && (
            <div className="rounded bg-slate-50 px-3 py-2 text-xs leading-5 dark:bg-[#0d1d2a]">
              <div className="mb-1 font-semibold">
                {t('chat.answerEvidencePlan')}
              </div>
              {(audit.answer_evidence_plan ?? []).map((plan, index) => (
                <div key={`${index}-${plan.claim}`} className="space-y-0.5">
                  <div>
                    {plan.claim}:{' '}
                    {(plan.fig_ids ?? [])
                      .map((figId) => formatFig(figId))
                      .filter(Boolean)
                      .join(', ') ||
                      plan.source_ids?.map((id) => `ID:${id}`).join(', ')}
                  </div>
                  <div className="opacity-80">
                    {plan.evidence_strength}
                    {plan.missing_evidence_reason
                      ? ` · ${plan.missing_evidence_reason}`
                      : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
