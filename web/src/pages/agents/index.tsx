import { EmptyCardType } from '@/components/empty/constant';
import { EmptyAppCard } from '@/components/empty/empty';
import ListFilterBar from '@/components/list-filter-bar';
import { RenameDialog } from '@/components/rename-dialog';
import { RAGFlowPagination } from '@/components/ui/ragflow-pagination';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { useFetchAgentListByPage } from '@/hooks/use-agent-request';
import { t } from 'i18next';
import { pick } from 'lodash';
import { LayoutTemplate, Plus } from 'lucide-react';
import { useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router';
import { CreateAgentDialog } from './create-agent-dialog';
import { HexAgentCard, HexCreateButton } from './hex-agent-card';
import { useCreateAgentOrPipeline } from './hooks/use-create-agent';
import { useSelectFilters } from './hooks/use-selelct-filters';
import { useRenameAgent } from './use-rename-agent';

export default function Agents() {
  const {
    data,
    pagination,
    setPagination,
    searchString,
    handleInputChange,
    filterValue,
    handleFilterSubmit,
  } = useFetchAgentListByPage();

  const {
    agentRenameLoading,
    initialAgentName,
    onAgentRenameOk,
    agentRenameVisible,
    hideAgentRenameModal,
    showAgentRenameModal,
  } = useRenameAgent();

  const {
    loading: createLoading,
    creatingVisible,
    hideCreatingModal,
    showCreatingModal,
    handleCreateAgentOrPipeline,
  } = useCreateAgentOrPipeline();

  const { navigateToAgentTemplates } = useNavigatePage();
  const filters = useSelectFilters();

  const handlePageChange = useCallback(
    (page: number, pageSize?: number) => {
      setPagination({ page, pageSize });
    },
    [setPagination],
  );

  const [searchUrl, setSearchUrl] = useSearchParams();
  const isCreate = searchUrl.get('isCreate') === 'true';

  useEffect(() => {
    if (isCreate) {
      searchUrl.delete('isCreate');
      setSearchUrl(searchUrl);
    }
  }, [isCreate, searchUrl, setSearchUrl]);

  const hasAgents = Boolean(data?.length);

  return (
    <>
      <article className="size-full flex flex-col" data-testid="agents-list">
        <header className="px-5 pt-8 mb-6">
          <ListFilterBar
            title={t('flow.agents')}
            searchString={searchString}
            onSearchChange={handleInputChange}
            icon="agents"
            filters={filters}
            onChange={handleFilterSubmit}
            value={filterValue}
          />
        </header>

        <div className="flex-1 overflow-auto px-5 pb-8 space-y-8">
          {/* Row 1 — create-action buttons (hidden when searching) */}
          {!searchString && (
            <div className="flex gap-6">
              <HexCreateButton
                icon={<LayoutTemplate className="size-9" />}
                label="从模板创建"
                onClick={navigateToAgentTemplates}
              />
              <HexCreateButton
                icon={<Plus className="size-9" />}
                label="手动编排"
                onClick={showCreatingModal}
              />
            </div>
          )}

          {/* Row 2 — agent hex cards */}
          {hasAgents && (
            <div className="flex flex-wrap gap-6">
              {data.map((x) => (
                <HexAgentCard
                  key={x.id}
                  data={x}
                  showAgentRenameModal={showAgentRenameModal}
                />
              ))}
            </div>
          )}

          {/* search empty */}
          {searchString && !hasAgents && (
            <div className="flex items-center justify-center h-64">
              <EmptyAppCard
                showIcon
                size="large"
                className="w-[480px] p-14"
                isSearch
                type={EmptyCardType.Agent}
              />
            </div>
          )}

          {/* pagination */}
          {hasAgents && (
            <RAGFlowPagination
              {...pick(pagination, 'current', 'pageSize')}
              total={pagination.total}
              onChange={handlePageChange}
            />
          )}
        </div>
      </article>

      {agentRenameVisible && (
        <RenameDialog
          hideModal={hideAgentRenameModal}
          onOk={onAgentRenameOk}
          initialName={initialAgentName}
          loading={agentRenameLoading}
        />
      )}

      {creatingVisible && (
        <CreateAgentDialog
          hideModal={hideCreatingModal}
          onOk={handleCreateAgentOrPipeline}
          loading={createLoading}
          shouldChooseAgent
        />
      )}
    </>
  );
}
