import { Button } from '@/components/ui/button';
import { useFeatureFlags } from '@/hooks/use-feature-flags';
import { Routes } from '@/routes';
import { ArrowLeft, BrainCircuit } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import {
  useDeleteMemoryProfileTopicMerge,
  useFetchMemoryProfile,
  useMergeMemoryProfileTopics,
  useRefreshMemoryProfile,
} from './hooks';
import { MemoThoughtPath } from './memo-thought-path';

export default function MemoryProfilePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { enabled } = useFeatureFlags();
  const { data, isLoading } = useFetchMemoryProfile();
  const { mutate: refreshProfile, isPending: isRefreshing } =
    useRefreshMemoryProfile();
  const { mutate: mergeTopics, isPending: isMergingTopics } =
    useMergeMemoryProfileTopics();
  const { mutate: deleteTopicMerge, isPending: isDeletingTopicMerge } =
    useDeleteMemoryProfileTopicMerge();
  const profile = data?.data;
  const profileEnabled =
    enabled('memoProfile') && profile?.feature_enabled !== false;

  return (
    <section className="flex h-full min-h-0 flex-col overflow-auto bg-bg-base px-6 py-5">
      <header className="mb-5 flex shrink-0 items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-xl bg-accent-primary/10 text-accent-primary">
            <BrainCircuit className="size-6" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold text-text-primary">
              {t('memories.profile.title', {
                defaultValue: 'Thinking profile',
              })}
            </h1>
            <p className="mt-1 text-sm text-text-secondary">
              {t('memories.profile.description', {
                defaultValue: 'Evidence-based topic activity from saved memos.',
              })}
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          className="shrink-0"
          onClick={() => navigate(Routes.Memories)}
        >
          <ArrowLeft className="size-4" />
          {t('memories.profile.backToSpacetime', {
            defaultValue: 'Back to spacetime',
          })}
        </Button>
      </header>

      <main className="min-h-0 flex-1">
        {!profileEnabled ? (
          <div className="flex h-64 flex-col items-center justify-center rounded-xl border border-border bg-bg-card/60 px-6 text-center">
            <BrainCircuit className="mb-4 size-10 text-text-secondary" />
            <h2 className="text-lg font-semibold text-text-primary">
              {t('memories.profile.disabledTitle', {
                defaultValue: 'Thinking profile is disabled',
              })}
            </h2>
            <p className="mt-2 max-w-xl text-sm leading-6 text-text-secondary">
              {t('memories.profile.disabledDescription', {
                defaultValue:
                  'The memo profile feature has been turned off by system configuration. Existing memos are still available in the memory list.',
              })}
            </p>
          </div>
        ) : profile ? (
          <MemoThoughtPath
            profile={profile}
            loading={isLoading}
            refreshing={isRefreshing}
            onRefresh={() => refreshProfile()}
            onMergeTopic={mergeTopics}
            onDeleteTopicMerge={deleteTopicMerge}
            mergingTopic={isMergingTopics}
            deletingTopicMerge={isDeletingTopicMerge}
          />
        ) : (
          <div className="flex h-64 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" />
          </div>
        )}
      </main>
    </section>
  );
}
