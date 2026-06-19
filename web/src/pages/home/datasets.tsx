import { HomeCard } from '@/components/home-card';
import { HomeIcon } from '@/components/svg-icon';
import { CardSkeleton } from '@/components/ui/skeleton';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { useFetchNextKnowledgeListByPage } from '@/hooks/use-knowledge-request';
import { Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

const HOME_DATASET_PAGE_SIZE = 12;

export function Datasets() {
  const { t } = useTranslation();
  const { kbs, loading } = useFetchNextKnowledgeListByPage({
    page: 1,
    pageSize: HOME_DATASET_PAGE_SIZE,
  });
  const { navigateToDataset, navigateToDatasetList } = useNavigatePage();

  return (
    <section className="rounded-xl bg-bg-base/70 p-5 shadow-sm ring-1 ring-border-default/20 dark:bg-bg-component/45">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center text-xl font-semibold leading-7">
            <HomeIcon imgClass="me-2.5" name="datasets" width={22} />
            {t('homeDashboard.knowledgeAssets')}
          </h2>
          <p className="mt-1 text-sm leading-6 text-text-secondary">
            {t('homeDashboard.knowledgeAssetsDescription')}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {kbs?.length > 0 && (
            <button
              type="button"
              className="rounded-full px-3 py-1.5 text-sm text-text-secondary transition hover:bg-bg-card hover:text-text-primary"
              onClick={() => navigateToDatasetList({ isCreate: false })}
            >
              {t('common.seeAll')}
            </button>
          )}
        </div>
      </header>

      <div>
        {loading ? (
          <div className="flex-1">
            <CardSkeleton />
          </div>
        ) : (
          <>
            {kbs?.length > 0 && (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                {kbs?.slice(0, HOME_DATASET_PAGE_SIZE).map((dataset) => (
                  <HomeCard
                    key={dataset.id}
                    data={{
                      ...dataset,
                      description: `${dataset.document_count} ${t('knowledgeDetails.files')}`,
                    }}
                    onClick={navigateToDataset(dataset.id)}
                    moreDropdown={null}
                  />
                ))}
                <button
                  type="button"
                  className="flex min-h-[104px] cursor-pointer items-center justify-center rounded-xl border border-dashed border-border/70 bg-bg-card/50 text-text-secondary transition hover:border-accent-primary hover:text-accent-primary"
                  onClick={() => navigateToDatasetList({ isCreate: true })}
                  aria-label={t('knowledgeList.createKnowledgeBase')}
                >
                  <Plus className="size-7" />
                </button>
              </div>
            )}
            {kbs?.length <= 0 && (
              <div className="rounded-lg bg-bg-card/45 px-4 py-8 text-center text-sm text-text-secondary">
                <div>{t('homeDashboard.emptySection')}</div>
                <button
                  type="button"
                  className="mt-4 rounded-full bg-accent-primary px-4 py-2 text-sm font-medium text-white transition hover:opacity-90"
                  onClick={() => navigateToDatasetList({ isCreate: true })}
                >
                  {t('knowledgeList.createKnowledgeBase')}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
