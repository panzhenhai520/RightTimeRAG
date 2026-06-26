import { CardContainer } from '@/components/card-container';
import { EmptyCardType } from '@/components/empty/constant';
import { EmptyAppCard } from '@/components/empty/empty';
import ListFilterBar from '@/components/list-filter-bar';
import { RenameDialog } from '@/components/rename-dialog';
import { Button } from '@/components/ui/button';
import { RAGFlowPagination } from '@/components/ui/ragflow-pagination';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { useFetchAgentListByPage } from '@/hooks/use-agent-request';
import { t } from 'i18next';
import { pick } from 'lodash';
import { LayoutTemplate, Plus } from 'lucide-react';
import { useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router';
import { AgentCard } from './agent-card';
import { CreateAgentDialog } from './create-agent-dialog';
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

  const createButtons = (
    <div className="flex items-center gap-2 shrink-0">
      <Button variant="outline" size="sm" onClick={navigateToAgentTemplates}>
        <LayoutTemplate className="size-4" />
        从模板创建
      </Button>
      <Button size="sm" onClick={showCreatingModal}>
        <Plus className="size-4" />
        手动编排
      </Button>
    </div>
  );

  return (
    <>
      {data?.length || searchString ? (
        <article className="size-full flex flex-col" data-testid="agents-list">
          <header className="px-5 pt-8 mb-4">
            <ListFilterBar
              title={t('flow.agents')}
              searchString={searchString}
              onSearchChange={handleInputChange}
              icon="agents"
              filters={filters}
              onChange={handleFilterSubmit}
              value={filterValue}
              leftPanel={createButtons}
            />
          </header>

          {data.length ? (
            <>
              <CardContainer className="flex-1 overflow-auto px-5">
                {data.map((x) => {
                  return (
                    <AgentCard
                      key={x.id}
                      data={x}
                      showAgentRenameModal={showAgentRenameModal}
                    />
                  );
                })}
              </CardContainer>

              <footer className="mt-4 px-5 pb-5">
                <RAGFlowPagination
                  {...pick(pagination, 'current', 'pageSize')}
                  total={pagination.total}
                  onChange={handlePageChange}
                />
              </footer>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <EmptyAppCard
                showIcon
                size="large"
                className="w-[480px] p-14"
                isSearch
                type={EmptyCardType.Agent}
              />
            </div>
          )}
        </article>
      ) : (
        <article className="size-full flex flex-col" data-testid="agents-list">
          <header className="px-5 pt-8 mb-4">
            <ListFilterBar
              title={t('flow.agents')}
              searchString={searchString}
              onSearchChange={handleInputChange}
              icon="agents"
              filters={filters}
              onChange={handleFilterSubmit}
              value={filterValue}
              leftPanel={createButtons}
            />
          </header>
          <div className="flex-1 flex items-center justify-center">
            <EmptyAppCard
              showIcon
              size="large"
              className="w-[480px] p-14 !cursor-default"
              type={EmptyCardType.Agent}
              tabIndex={-1}
            />
          </div>
        </article>
      )}

      {agentRenameVisible && (
        <RenameDialog
          hideModal={hideAgentRenameModal}
          onOk={onAgentRenameOk}
          initialName={initialAgentName}
          loading={agentRenameLoading}
        ></RenameDialog>
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
