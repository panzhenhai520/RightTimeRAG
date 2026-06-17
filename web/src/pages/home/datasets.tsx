import { CardSineLineContainer } from '@/components/card-singleline-container';
import { HomeCard } from '@/components/home-card';
import { HomeIcon } from '@/components/svg-icon';
import { CardSkeleton } from '@/components/ui/skeleton';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { useFetchNextKnowledgeListByPage } from '@/hooks/use-knowledge-request';
import { useTranslation } from 'react-i18next';
import { SeeAllAppCard } from './application-card';

export function Datasets() {
  const { t } = useTranslation();
  const { kbs, loading } = useFetchNextKnowledgeListByPage();
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
        {kbs?.length > 0 && (
          <button
            type="button"
            className="shrink-0 rounded-full px-3 py-1.5 text-sm text-text-secondary transition hover:bg-bg-card hover:text-text-primary"
            onClick={() => navigateToDatasetList({ isCreate: false })}
          >
            {t('common.seeAll')}
          </button>
        )}
      </header>

      <div>
        {loading ? (
          <div className="flex-1">
            <CardSkeleton />
          </div>
        ) : (
          <>
            {kbs?.length > 0 && (
              <CardSineLineContainer className="gap-4 xl:grid-cols-3 2xl:grid-cols-4">
                {kbs?.slice(0, 6).map((dataset) => (
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
                <SeeAllAppCard
                  click={() => navigateToDatasetList({ isCreate: false })}
                />
              </CardSineLineContainer>
            )}
            {kbs?.length <= 0 && (
              <div className="rounded-lg bg-bg-card/45 px-4 py-8 text-center text-sm text-text-secondary">
                {t('homeDashboard.emptySection')}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
