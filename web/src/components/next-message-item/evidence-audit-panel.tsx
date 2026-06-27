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
  defaultExpanded?: boolean;
};

const evidenceTypeClass: Record<string, string> = {
  original_text:
    'border-emerald-200 bg-emerald-50 text-emerald-800 dark:!border-[#6dbf96]/36 dark:!bg-[#24463f] dark:!text-[#d7f1e6] dark:hover:!bg-[#2a5248]',
  raptor_summary_with_sources:
    'border-amber-200 bg-amber-50 text-amber-800 dark:!border-[#b79a5a]/34 dark:!bg-[#4a402b] dark:!text-[#ead6a2] dark:hover:!bg-[#574b33]',
  raptor_summary:
    'border-amber-200 bg-amber-50 text-amber-800 dark:!border-[#b79a5a]/34 dark:!bg-[#4a402b] dark:!text-[#ead6a2] dark:hover:!bg-[#574b33]',
  title_only:
    'border-slate-200 bg-slate-50 text-slate-700 dark:!border-[#7aa4ba]/30 dark:!bg-[#243d4e] dark:!text-[#cbdfe9] dark:hover:!bg-[#2a4658]',
  weak_context:
    'border-slate-200 bg-slate-50 text-slate-700 dark:!border-[#7aa4ba]/30 dark:!bg-[#243d4e] dark:!text-[#cbdfe9] dark:hover:!bg-[#2a4658]',
};

const formatFig = (figId?: number) =>
  typeof figId === 'number' && Number.isFinite(figId) ? `Fig.${figId + 1}` : '';

// Maps the backend evidence_strength values to a localized label + badge color.
const strengthMeta: Record<string, { key: string; className: string }> = {
  strong: {
    key: 'chat.evidenceStrengthStrong',
    className:
      'border-emerald-200 bg-emerald-50 text-emerald-700 dark:!border-[#6dbf96]/38 dark:!bg-[#23483f] dark:!text-[#c5eddc]',
  },
  medium: {
    key: 'chat.evidenceStrengthMedium',
    className:
      'border-amber-200 bg-amber-50 text-amber-700 dark:!border-[#b79a5a]/38 dark:!bg-[#4a402b] dark:!text-[#ead6a2]',
  },
  weak: {
    key: 'chat.evidenceStrengthWeak',
    className:
      'border-slate-200 bg-slate-100 text-slate-600 dark:!border-[#7aa4ba]/32 dark:!bg-[#243d4e] dark:!text-[#c7dce7]',
  },
  unknown: {
    key: 'chat.evidenceStrengthUnknown',
    className:
      'border-slate-200 bg-slate-100 text-slate-500 dark:!border-[#7aa4ba]/28 dark:!bg-[#213847] dark:!text-[#b8d0dc]',
  },
};

export function EvidenceAuditPanel({ audit, defaultExpanded = false }: IProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const citedEvidence = useMemo(
    () => (audit?.evidence ?? []).filter((item) => item.is_cited),
    [audit?.evidence],
  );
  const visibleEvidence = citedEvidence.length
    ? citedEvidence
    : (audit?.evidence ?? []).slice(0, 4);

  if (!audit) {
    return null;
  }

  const warnings = audit.warnings ?? [];
  const candidateChunks = audit.retrieval?.candidate_chunks ?? 0;
  const candidateDocs = audit.retrieval?.candidate_docs ?? 0;
  const selectedChunks = audit.retrieval?.selected_chunks ?? 0;
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
    <section className="mt-2 w-full max-w-3xl rounded-md border border-[#d9c7cf] bg-white/72 p-3 text-sm text-slate-700 shadow-sm dark:!border-[#7aa4ba]/34 dark:!bg-[#1b3444] dark:!text-[#dcebf3] dark:shadow-[0_8px_24px_rgba(4,25,39,0.1)]">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 rounded px-1 py-1 text-left transition-colors hover:bg-slate-100/70 dark:hover:!bg-[#2a4658]"
        onClick={() => setExpanded((value) => !value)}
      >
        <span className="inline-flex items-center gap-2 font-semibold text-[#5b2737] dark:text-[#e7f5fb]">
          <FileText className="size-4" />
          {t('chat.evidenceAudit')}
        </span>
        <span className="inline-flex items-center gap-3 text-xs text-slate-500 dark:text-[#b8d0dc]">
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
            <div className="rounded border border-transparent bg-slate-50 px-3 py-2 text-xs leading-5 text-slate-600 dark:!border-[#7aa4ba]/28 dark:!bg-[#243d4e] dark:!text-[#c6dbe6]">
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
                  className="flex gap-2 rounded border border-transparent bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:!border-[#b79a5a]/34 dark:!bg-[#4a402b] dark:!text-[#ead6a2]"
                >
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                  <span>{warning}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-col gap-2">
            {visibleEvidence.map((item) => (
              <article
                key={`${item.id}-${item.chunk_id}`}
                className={cn(
                  'min-w-0 rounded border p-2 transition-colors',
                  evidenceTypeClass[item.type] ??
                    'border-slate-200 bg-slate-50 text-slate-700 dark:!border-[#7aa4ba]/30 dark:!bg-[#243d4e] dark:!text-[#cbdfe9] dark:hover:!bg-[#2a4658]',
                )}
              >
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {item.is_cited && (
                    <CheckCircle2 className="size-3.5 shrink-0" />
                  )}
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
                  <div className="mt-1 break-words text-xs leading-5">
                    {item.why}
                  </div>
                )}
                {item.preview && (
                  <div className="mt-1 line-clamp-2 break-words text-xs leading-5 opacity-85">
                    {item.preview}
                  </div>
                )}
              </article>
            ))}
          </div>

          {(audit.answer_basis ?? []).length > 0 && (
            <div className="rounded border border-transparent bg-slate-50 px-3 py-2 text-xs leading-5 dark:!border-[#7aa4ba]/28 dark:!bg-[#243d4e] dark:!text-[#d8e8f0]">
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
            <div className="rounded border border-transparent bg-slate-50 px-3 py-2 text-xs leading-5 dark:!border-[#7aa4ba]/28 dark:!bg-[#243d4e] dark:!text-[#d8e8f0]">
              <div className="mb-0.5 font-semibold">
                {t('chat.answerEvidencePlan')}
              </div>
              <div className="mb-2 opacity-70">
                {t('chat.answerEvidencePlanHint')}
              </div>
              <div className="space-y-2">
                {(audit.answer_evidence_plan ?? []).map((plan, index) => {
                  const cites =
                    (plan.fig_ids ?? [])
                      .map((figId) => formatFig(figId))
                      .filter(Boolean)
                      .join(', ') ||
                    plan.source_ids?.map((id) => `ID:${id}`).join(', ') ||
                    '';
                  const meta =
                    strengthMeta[plan.evidence_strength ?? 'unknown'] ??
                    strengthMeta.unknown;
                  return (
                    <div
                      key={`${index}-${plan.claim}`}
                      className="min-w-0 space-y-1"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={cn(
                            'shrink-0 rounded border px-1.5 py-0.5 text-[11px] font-medium',
                            meta.className,
                          )}
                        >
                          {t(meta.key)}
                        </span>
                        {cites && (
                          <span className="min-w-0 break-words">
                            {t('chat.evidenceCitesLabel')}: {cites}
                          </span>
                        )}
                      </div>
                      {plan.missing_evidence_reason && (
                        <div className="break-words opacity-80">
                          {plan.missing_evidence_reason}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
