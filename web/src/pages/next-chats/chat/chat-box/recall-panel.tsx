import { EvidenceAuditPanel } from '@/components/next-message-item/evidence-audit-panel';
import { ReferenceDocumentList } from '@/components/next-message-item/reference-document-list';
import { useFeatureFlags } from '@/hooks/use-feature-flags';
import { Docagg, IReference } from '@/interfaces/database/chat';
import { cn } from '@/lib/utils';
import {
  ChevronLeft,
  ChevronRight,
  FileSearch,
  Loader2,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

type IProps = {
  reference?: IReference;
  /** True while the latest answer is still streaming. */
  loading?: boolean;
  /** Controlled width in px (driven by the draggable splitter). */
  width?: number;
  /** Whether the panel is in the enlarged (maximized) state. */
  expanded?: boolean;
  /** Toggle the enlarged state. */
  onToggleExpand?: () => void;
  /** Toggle the collapsed state. */
  onToggleCollapse?: () => void;
  /** Whether the panel is currently collapsed. */
  collapsed?: boolean;
  className?: string;
};

/**
 * Right-side recall zone. Shows retrieved documents (available early, via the
 * backend evidence_preview event) and the evidence audit (available only after
 * the answer completes). Decoupling these from the streaming answer text keeps
 * them visible without scrolling past the growing answer.
 */
export function RecallPanel({
  reference,
  loading = false,
  width,
  expanded = false,
  onToggleExpand,
  onToggleCollapse,
  collapsed = false,
  className,
}: IProps) {
  const { t } = useTranslation();
  const { enabled } = useFeatureFlags();
  const evidenceAuditEnabled = enabled('evidenceAudit');

  const citedDocumentIds = useMemo(
    () =>
      new Set(
        (reference?.chunks ?? [])
          .map((chunk) => chunk.document_id)
          .filter(Boolean),
      ),
    [reference?.chunks],
  );

  const documentList: Docagg[] = useMemo(() => {
    const docAggs = reference?.doc_aggs ?? [];
    // When no chunk carries a document_id (KG / web-search chunks), fall back to
    // showing every retrieved document rather than hiding the panel.
    if (citedDocumentIds.size === 0) return docAggs;
    return docAggs.filter((doc) => citedDocumentIds.has(doc.doc_id));
  }, [citedDocumentIds, reference?.doc_aggs]);

  const audit = reference?.evidence_audit;
  const hasDocuments = documentList.length > 0;
  const hasContent = hasDocuments || Boolean(audit) || loading;

  return (
    <aside
      style={width ? { width } : undefined}
      className={cn(
        'flex h-full shrink-0 flex-col overflow-auto scrollbar-auto border-l border-transparent bg-white/35 px-4 py-5 dark:!border-[#7aa4ba]/26 dark:!bg-[#183243]',
        width ? '' : 'w-[340px]',
        collapsed && 'px-2 py-4',
        className,
      )}
      data-testid="chat-recall-panel"
    >
      <header className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-primary dark:text-[#e7f5fb]">
        <FileSearch className="size-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">
          {t('chat.recallPanelTitle')}
        </span>
        {onToggleCollapse && (
          <button
            type="button"
            className="shrink-0 rounded p-1 text-text-secondary transition-colors hover:bg-bg-card hover:text-text-primary dark:hover:!bg-[#2a4658] dark:hover:text-[#f2fbff]"
            onClick={onToggleCollapse}
            title={t(collapsed ? 'chat.recallExpand' : 'chat.recallCollapse')}
            aria-label={t(
              collapsed ? 'chat.recallExpand' : 'chat.recallCollapse',
            )}
            data-testid="chat-recall-collapse-toggle"
          >
            {collapsed ? (
              <ChevronLeft className="size-4" />
            ) : (
              <ChevronRight className="size-4" />
            )}
          </button>
        )}
        {onToggleExpand && (
          <button
            type="button"
            className="shrink-0 rounded p-1 text-text-secondary transition-colors hover:bg-bg-card hover:text-text-primary dark:hover:!bg-[#2a4658] dark:hover:text-[#f2fbff]"
            onClick={onToggleExpand}
            title={t(expanded ? 'chat.recallCollapse' : 'chat.recallExpand')}
            aria-label={t(
              expanded ? 'chat.recallCollapse' : 'chat.recallExpand',
            )}
            data-testid="chat-recall-expand-toggle"
          >
            {expanded ? (
              <Minimize2 className="size-4" />
            ) : (
              <Maximize2 className="size-4" />
            )}
          </button>
        )}
      </header>

      {collapsed ? (
        <div className="flex-1" />
      ) : !hasContent ? (
        <div className="mt-6 text-center text-xs leading-6 text-text-secondary">
          {t('chat.recallEmpty')}
        </div>
      ) : (
        <>
          {evidenceAuditEnabled && audit && (
            <EvidenceAuditPanel audit={audit} defaultExpanded />
          )}

          {evidenceAuditEnabled && !audit && loading && (
            <div className="mt-2 flex items-center gap-2 rounded-md border border-border bg-bg-card px-3 py-2 text-xs text-text-secondary dark:!border-[#7aa4ba]/34 dark:!bg-[#243d4e] dark:!text-[#c5dbe7]">
              <Loader2 className="size-3.5 animate-spin" />
              {t('chat.recallEvidenceAnalyzing')}
            </div>
          )}

          {hasDocuments && (
            <div className="mt-3">
              <div className="mb-1 text-xs font-medium text-text-secondary">
                {t('chat.recallDocuments')} ·{' '}
                {t('chat.recallDocumentsCount', { count: documentList.length })}
              </div>
              <ReferenceDocumentList list={documentList} dense />
            </div>
          )}
        </>
      )}
    </aside>
  );
}
