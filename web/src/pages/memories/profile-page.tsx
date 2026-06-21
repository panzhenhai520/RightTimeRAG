import { Button } from '@/components/ui/button';
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
  const { data, isLoading } = useFetchMemoryProfile();
  const { mutate: refreshProfile, isPending: isRefreshing } =
    useRefreshMemoryProfile();
  const { mutate: mergeTopics, isPending: isMergingTopics } =
    useMergeMemoryProfileTopics();
  const { mutate: deleteTopicMerge, isPending: isDeletingTopicMerge } =
    useDeleteMemoryProfileTopicMerge();
  const profile = data?.data;

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
        {profile ? (
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
