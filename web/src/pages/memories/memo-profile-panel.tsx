import { Button } from '@/components/ui/button';
import { formatDate } from '@/utils/date';
import {
  Activity,
  ExternalLink,
  GitBranch,
  Route,
  TrendingUp,
} from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type {
  MemoProfileInput,
  MemoProfileMetrics,
  MemoTopicTrend,
  MemoTopicTrendType,
} from './memo-profile';

type MemoProfilePanelProps = {
  inputs: MemoProfileInput[];
  metrics: MemoProfileMetrics;
  trends: MemoTopicTrend[];
  onOpenMemory: (memoryId: string) => void;
};

const TREND_CLASSNAME: Record<MemoTopicTrendType, string> = {
  emerging: 'text-accent-primary',
  stable: 'text-text-secondary',
  declining: 'text-amber-600 dark:text-amber-300',
};

export function MemoProfilePanel({
  inputs,
  metrics,
  trends,
  onOpenMemory,
}: MemoProfilePanelProps) {
  const { t } = useTranslation();
  const topTopics = metrics.topics.slice(0, 4);
  const learningPath = [...metrics.topics]
    .sort((a, b) => a.firstSeen - b.firstSeen)
    .slice(0, 5);
  const recentMemos = useMemo(
    () => [...inputs].sort((a, b) => b.createdAt - a.createdAt).slice(0, 4),
    [inputs],
  );

  if (!inputs.length) return null;

  return (
    <div className="space-y-3 rounded-lg bg-bg-card/50 p-3">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
          <Activity className="size-4 text-accent-primary" />
          {t('memories.profile.title', {
            defaultValue: 'Thinking profile',
          })}
        </div>
        <p className="mt-1 text-xs leading-5 text-text-secondary">
          {t('memories.profile.description', {
            defaultValue:
              'Evidence-based topic activity from your saved memos.',
          })}
        </p>
      </div>

      <section className="space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-text-primary">
          <TrendingUp className="size-3.5 text-accent-primary" />
          {t('memories.profile.topTopics', {
            defaultValue: 'Top topics',
          })}
        </div>
        <div className="space-y-1.5">
          {topTopics.map((topic) => (
            <button
              className="w-full rounded-md bg-bg-base/55 px-2 py-1.5 text-left text-xs transition hover:bg-accent-primary/10"
              key={topic.topicId}
              onClick={() => onOpenMemory(topic.memoryIds[0])}
            >
              <div className="truncate font-medium text-text-primary">
                {topic.topicLabel}
              </div>
              <div className="mt-0.5 text-text-secondary">
                {t('memories.profile.topicStats', {
                  defaultValue: '{{memos}} memos · {{turns}} turns',
                  memos: topic.memoCount,
                  turns: topic.turnCount,
                })}
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-text-primary">
          <Route className="size-3.5 text-accent-primary" />
          {t('memories.profile.learningPath', {
            defaultValue: 'Learning path',
          })}
        </div>
        <div className="space-y-1 text-xs text-text-secondary">
          {learningPath.map((topic, index) => (
            <div className="flex items-center gap-2" key={topic.topicId}>
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent-primary/10 text-[10px] text-accent-primary">
                {index + 1}
              </span>
              <span className="truncate">{topic.topicLabel}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-text-primary">
          <GitBranch className="size-3.5 text-accent-primary" />
          {t('memories.profile.recentChanges', {
            defaultValue: 'Recent changes',
          })}
        </div>
        <div className="space-y-1.5">
          {trends.slice(0, 4).map((trend) => (
            <div
              className="rounded-md bg-bg-base/55 px-2 py-1.5 text-xs"
              key={trend.topicId}
            >
              <div className="truncate font-medium text-text-primary">
                {trend.topicLabel}
              </div>
              <div className={TREND_CLASSNAME[trend.trend]}>
                {t(`memories.profile.trends.${trend.trend}`, {
                  defaultValue: trend.trend,
                })}
                {' · '}
                {trend.activityDelta > 0 ? '+' : ''}
                {trend.activityDelta}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-text-primary">
          <ExternalLink className="size-3.5 text-accent-primary" />
          {t('memories.profile.traceableMemos', {
            defaultValue: 'Traceable memos',
          })}
        </div>
        <div className="space-y-1.5">
          {recentMemos.map((memo) => (
            <Button
              className="h-auto w-full justify-between px-2 py-1.5 text-left text-xs"
              key={memo.memoryId}
              size="sm"
              variant="outline"
              onClick={() => onOpenMemory(memo.memoryId)}
            >
              <span className="min-w-0 flex-1 truncate">
                {memo.displayTitle}
              </span>
              <span className="ml-2 shrink-0 text-[10px] text-text-secondary">
                {formatDate(memo.createdAt)}
              </span>
            </Button>
          ))}
        </div>
      </section>
    </div>
  );
}
