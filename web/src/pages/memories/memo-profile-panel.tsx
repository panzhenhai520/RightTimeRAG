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
  variant?: 'compact' | 'full';
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
  variant = 'compact',
}: MemoProfilePanelProps) {
  const { t } = useTranslation();
  const isFull = variant === 'full';
  const topTopics = metrics.topics.slice(0, isFull ? 12 : 4);
  const learningPath = [...metrics.topics]
    .sort((a, b) => a.firstSeen - b.firstSeen)
    .slice(0, isFull ? 20 : 5);
  const recentMemos = useMemo(
    () =>
      [...inputs]
        .sort((a, b) => b.createdAt - a.createdAt)
        .slice(0, isFull ? 24 : 4),
    [inputs, isFull],
  );

  if (!inputs.length) {
    if (!isFull) return null;
    return (
      <div className="rounded-xl bg-bg-card/60 p-8 text-center">
        <Activity className="mx-auto mb-3 size-9 text-accent-primary" />
        <div className="text-lg font-semibold text-text-primary">
          {t('memories.profile.emptyTitle', {
            defaultValue: 'No profile data yet',
          })}
        </div>
        <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
          {t('memories.profile.emptyDescription', {
            defaultValue:
              'The thinking profile is generated from saved memo messages. Save chat sessions to memo first, then the profile will show topic evidence, learning path, recent changes, and traceable memos.',
          })}
        </p>
      </div>
    );
  }

  const inputById = new Map(inputs.map((input) => [input.memoryId, input]));
  const sourceKindLabel = (kind: string) =>
    t(`memories.profile.sourceKinds.${kind}`, { defaultValue: kind });
  const sourceKindsText = (sourceKinds: string[]) =>
    sourceKinds.map(sourceKindLabel).join(' / ');

  return (
    <div
      className={
        isFull ? 'space-y-5' : 'space-y-3 rounded-lg bg-bg-card/50 p-3'
      }
    >
      <div>
        <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
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
        {isFull && (
          <div className="mt-3 rounded-xl bg-bg-card/70 p-4 text-sm leading-6 text-text-secondary">
            <div className="mb-1 font-medium text-text-primary">
              {t('memories.profile.whatIsProfile', {
                defaultValue: 'What this profile means',
              })}
            </div>
            {t('memories.profile.whatIsProfileDescription', {
              defaultValue:
                'This page does not infer your personality. It summarizes the topics, evidence density, time order, and recent activity from saved memo records so each conclusion can be traced back to concrete memos.',
            })}
          </div>
        )}
      </div>

      <section className="space-y-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-text-primary">
          <TrendingUp className="size-3.5 text-accent-primary" />
          {t('memories.profile.topTopics', {
            defaultValue: 'Top topics',
          })}
        </div>
        <div
          className={
            isFull ? 'grid gap-3 md:grid-cols-2 xl:grid-cols-3' : 'space-y-1.5'
          }
        >
          {topTopics.map((topic) => (
            <button
              className={
                isFull
                  ? 'min-h-40 w-full rounded-xl bg-bg-card/70 p-4 text-left text-sm transition hover:bg-accent-primary/10'
                  : 'w-full rounded-md bg-bg-base/55 px-2 py-1.5 text-left text-xs transition hover:bg-accent-primary/10'
              }
              key={topic.topicId}
              onClick={() => onOpenMemory(topic.memoryIds[0])}
            >
              <div className="truncate font-semibold text-text-primary">
                {topic.topicLabel}
              </div>
              <div className="mt-0.5 text-text-secondary">
                {t('memories.profile.topicStats', {
                  defaultValue: '{{memos}} memos · {{turns}} turns',
                  memos: topic.memoCount,
                  turns: topic.turnCount,
                })}
              </div>
              {isFull && (
                <div className="mt-3 space-y-2 text-xs leading-5 text-text-secondary">
                  <div>
                    {t('memories.profile.activeDays', {
                      defaultValue: 'Active days',
                    })}
                    :{' '}
                    <span className="font-medium text-text-primary">
                      {topic.activeDays}
                    </span>
                  </div>
                  <div>
                    {t('memories.profile.sources', {
                      defaultValue: 'Sources',
                    })}
                    : {sourceKindsText(topic.sourceKinds)}
                  </div>
                  {!!topic.keywords.length && (
                    <div className="flex flex-wrap gap-1">
                      {topic.keywords.slice(0, 6).map((keyword) => (
                        <span
                          className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-[11px] text-accent-primary"
                          key={keyword}
                        >
                          {keyword}
                        </span>
                      ))}
                    </div>
                  )}
                  <div>
                    {t('memories.profile.evidenceMemos', {
                      defaultValue: 'Evidence memos',
                    })}
                    :{' '}
                    {topic.memoryIds
                      .slice(0, 3)
                      .map((id) => inputById.get(id)?.displayTitle || id)
                      .join(' / ')}
                  </div>
                </div>
              )}
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
        <div
          className={
            isFull
              ? 'grid gap-3 md:grid-cols-2 xl:grid-cols-4'
              : 'space-y-1 text-xs text-text-secondary'
          }
        >
          {learningPath.map((topic, index) => (
            <button
              className={
                isFull
                  ? 'flex min-h-24 w-full items-start gap-3 rounded-xl bg-bg-card/70 p-4 text-left transition hover:bg-accent-primary/10'
                  : 'flex w-full items-center gap-2 rounded-md px-1 py-1 text-left transition hover:bg-accent-primary/10'
              }
              key={topic.topicId}
              onClick={() => onOpenMemory(topic.memoryIds[0])}
            >
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent-primary/10 text-[10px] text-accent-primary">
                {index + 1}
              </span>
              <span className="min-w-0">
                <span className="block truncate font-medium text-text-primary">
                  {topic.topicLabel}
                </span>
                {isFull && (
                  <span className="mt-1 block text-xs leading-5 text-text-secondary">
                    {formatDate(topic.firstSeen)} ·{' '}
                    {t('memories.profile.topicStats', {
                      defaultValue: '{{memos}} memos · {{turns}} turns',
                      memos: topic.memoCount,
                      turns: topic.turnCount,
                    })}
                  </span>
                )}
              </span>
            </button>
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
        <div
          className={
            isFull ? 'grid gap-3 md:grid-cols-2 xl:grid-cols-3' : 'space-y-1.5'
          }
        >
          {trends.slice(0, isFull ? 12 : 4).map((trend) => (
            <button
              className={
                isFull
                  ? 'min-h-32 w-full rounded-xl bg-bg-card/70 p-4 text-left text-sm transition hover:bg-accent-primary/10'
                  : 'w-full rounded-md bg-bg-base/55 px-2 py-1.5 text-left text-xs transition hover:bg-accent-primary/10'
              }
              key={trend.topicId}
              onClick={() => onOpenMemory(trend.evidenceMemoryIds[0])}
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
              {isFull && (
                <div className="mt-2 space-y-1 text-xs leading-5 text-text-secondary">
                  <div>
                    {t('memories.profile.recentPeriod', {
                      defaultValue: 'Recent',
                    })}
                    : {trend.recentMemoCount}{' '}
                    {t('memories.spacetime.totalMemos', {
                      defaultValue: 'Memos',
                    })}{' '}
                    / {trend.recentTurnCount}{' '}
                    {t('memories.spacetime.totalTurns', {
                      defaultValue: 'turns',
                    })}
                  </div>
                  <div>
                    {t('memories.profile.previousPeriod', {
                      defaultValue: 'Previous',
                    })}
                    : {trend.previousMemoCount}{' '}
                    {t('memories.spacetime.totalMemos', {
                      defaultValue: 'Memos',
                    })}{' '}
                    / {trend.previousTurnCount}{' '}
                    {t('memories.spacetime.totalTurns', {
                      defaultValue: 'turns',
                    })}
                  </div>
                  <div>
                    {t('memories.profile.evidenceMemos', {
                      defaultValue: 'Evidence memos',
                    })}
                    :{' '}
                    {trend.evidenceMemoryIds
                      .slice(0, 2)
                      .map((id) => inputById.get(id)?.displayTitle || id)
                      .join(' / ')}
                  </div>
                </div>
              )}
            </button>
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
        <div
          className={
            isFull ? 'grid gap-3 md:grid-cols-2 xl:grid-cols-3' : 'space-y-1.5'
          }
        >
          {recentMemos.map((memo) => (
            <Button
              className={
                isFull
                  ? 'h-auto min-h-36 w-full flex-col items-start justify-start gap-2 p-4 text-left text-sm'
                  : 'h-auto w-full justify-between px-2 py-1.5 text-left text-xs'
              }
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
              {isFull && memo.summary && (
                <span className="line-clamp-4 whitespace-pre-line text-xs leading-5 text-text-secondary">
                  {memo.summary}
                </span>
              )}
            </Button>
          ))}
        </div>
      </section>
    </div>
  );
}
