import { useFetchKnowledgeList } from '@/hooks/use-knowledge-request';
import { cn } from '@/lib/utils';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';

type SearchDatasetChipsProps = {
  kbIds?: string[];
  className?: string;
  maxVisible?: number;
};

export default function SearchDatasetChips({
  kbIds = [],
  className,
  maxVisible = 8,
}: SearchDatasetChipsProps) {
  const { t } = useTranslation();
  const { list, loading } = useFetchKnowledgeList();

  const datasetNames = useMemo(() => {
    const byId = new Map(list.map((item) => [item.id, item.name]));
    return kbIds.map((id) => byId.get(id) || `${id.slice(0, 8)}...`);
  }, [kbIds, list]);

  if (kbIds.length === 0) return null;

  const visibleNames = datasetNames.slice(0, maxVisible);
  const hiddenCount = Math.max(datasetNames.length - visibleNames.length, 0);

  return (
    <div
      className={cn(
        'mt-3 flex flex-wrap items-center justify-center gap-2 text-xs text-text-secondary',
        className,
      )}
    >
      <span className="shrink-0">{t('search.datasets')}</span>
      {visibleNames.map((name, index) => (
        <span
          key={`${kbIds[index]}-${name}`}
          className="max-w-44 truncate rounded-full bg-accent-primary/10 px-2.5 py-1 text-accent-primary ring-1 ring-accent-primary/10 dark:bg-white/10 dark:text-white/80 dark:ring-white/10"
          title={name}
        >
          {name}
        </span>
      ))}
      {hiddenCount > 0 && (
        <span className="rounded-full bg-bg-card px-2.5 py-1 text-text-secondary">
          +{hiddenCount}
        </span>
      )}
      {loading && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-primary/70" />
      )}
    </div>
  );
}
