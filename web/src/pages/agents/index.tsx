import { EmptyCardType } from '@/components/empty/constant';
import { EmptyAppCard } from '@/components/empty/empty';
import ListFilterBar from '@/components/list-filter-bar';
import { RenameDialog } from '@/components/rename-dialog';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { useFetchAgentListByPage } from '@/hooks/use-agent-request';
import { IFlow } from '@/interfaces/database/agent';
import { t } from 'i18next';
import {
  BookOpenText,
  GraduationCap,
  LayoutTemplate,
  Plus,
} from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { CreateAgentDialog } from './create-agent-dialog';
import {
  HexAgentCard,
  HexCreateButton,
  HexEmptyCell,
  HexTile,
} from './hex-agent-card';
import { useCreateAgentOrPipeline } from './hooks/use-create-agent';
import styles from './index.module.less';
import { useRenameAgent } from './use-rename-agent';

type HoneycombCell =
  | { type: 'creation-guide' }
  | { type: 'creation-case' }
  | { type: 'create-template' }
  | { type: 'create-manual' }
  | { type: 'agent'; data: IFlow }
  | { type: 'empty'; id: string };

const MIN_HONEYCOMB_CELLS = 24;
const HONEYCOMB_ROW_SIZE = 8;

function fillHoneycombCells(cells: HoneycombCell[]) {
  const targetCount = Math.max(
    MIN_HONEYCOMB_CELLS,
    Math.ceil((cells.length + 4) / HONEYCOMB_ROW_SIZE) * HONEYCOMB_ROW_SIZE,
  );
  const emptyCount = Math.max(0, targetCount - cells.length);

  return [
    ...cells,
    ...Array.from({ length: emptyCount }, (_, index) => ({
      type: 'empty' as const,
      id: `empty-${index}`,
    })),
  ];
}

export default function Agents() {
  const { data, searchString } = useFetchAgentListByPage({
    page: 1,
    pageSize: 100000,
  });

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

  const {
    navigateToAgentTemplates,
    navigateToAgentCreationGuide,
    navigateToAgentCreationCase,
  } = useNavigatePage();

  const [searchUrl, setSearchUrl] = useSearchParams();
  const isCreate = searchUrl.get('isCreate') === 'true';

  useEffect(() => {
    if (isCreate) {
      searchUrl.delete('isCreate');
      setSearchUrl(searchUrl);
    }
  }, [isCreate, searchUrl, setSearchUrl]);

  const hasAgents = Boolean(data?.length);
  const honeycombCells = useMemo(() => {
    const actionCells: HoneycombCell[] = searchString
      ? []
      : [
          { type: 'creation-guide' },
          { type: 'creation-case' },
          { type: 'create-template' },
          { type: 'create-manual' },
        ];
    const agentCells: HoneycombCell[] = data.map((agent) => ({
      type: 'agent',
      data: agent,
    }));

    return fillHoneycombCells([...actionCells, ...agentCells]);
  }, [data, searchString]);

  return (
    <>
      <article
        className={`size-full flex flex-col ${styles.agentShell}`}
        data-testid="agents-list"
      >
        <header className="px-5 pt-8 mb-6 shrink-0">
          <ListFilterBar
            title={t('flow.agents')}
            searchString={searchString}
            icon="agents"
            showFilter={false}
            showSearch={false}
          />
        </header>

        <div className={styles.honeycombPage}>
          <div className={styles.honeycombGrid}>
            {honeycombCells.map((cell, index) => {
              if (cell.type === 'creation-guide') {
                return (
                  <HexTile key={cell.type} index={index}>
                    <HexCreateButton
                      icon={<BookOpenText className="size-6" />}
                      label="智能体创建指南"
                      onClick={navigateToAgentCreationGuide}
                    />
                  </HexTile>
                );
              }

              if (cell.type === 'creation-case') {
                return (
                  <HexTile key={cell.type} index={index}>
                    <HexCreateButton
                      icon={<GraduationCap className="size-6" />}
                      label="智能体创建案例"
                      onClick={navigateToAgentCreationCase}
                    />
                  </HexTile>
                );
              }

              if (cell.type === 'create-template') {
                return (
                  <HexTile key={cell.type} index={index}>
                    <HexCreateButton
                      icon={<LayoutTemplate className="size-6" />}
                      label="从模板创建"
                      onClick={navigateToAgentTemplates}
                    />
                  </HexTile>
                );
              }

              if (cell.type === 'create-manual') {
                return (
                  <HexTile key={cell.type} index={index}>
                    <HexCreateButton
                      icon={<Plus className="size-6" />}
                      label="手动创建"
                      onClick={showCreatingModal}
                    />
                  </HexTile>
                );
              }

              if (cell.type === 'agent') {
                return (
                  <HexTile key={cell.data.id} index={index}>
                    <HexAgentCard
                      data={cell.data}
                      showAgentRenameModal={showAgentRenameModal}
                    />
                  </HexTile>
                );
              }

              return (
                <HexTile key={cell.id} index={index}>
                  <HexEmptyCell />
                </HexTile>
              );
            })}
          </div>

          {searchString && !hasAgents && (
            <div className={styles.searchEmpty}>
              <EmptyAppCard
                showIcon
                size="large"
                className="w-[480px] p-14"
                isSearch
                type={EmptyCardType.Agent}
              />
            </div>
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
