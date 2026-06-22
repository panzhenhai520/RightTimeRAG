import { EmptyCardType } from '@/components/empty/constant';
import { EmptyAppCard } from '@/components/empty/empty';
import { Button } from '@/components/ui/button';
import { useTranslate } from '@/hooks/common-hooks';
import { useFeatureFlags } from '@/hooks/use-feature-flags';
import { Plus } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { AddOrEditModal } from './add-or-edit-modal';
import { defaultMemoryFields } from './constants';
import { useFetchMemoryList, useRenameMemory } from './hooks';
import { ICreateMemoryProps, IMemory } from './interface';
import { MemoSpacetimeNetwork } from './memo-spacetime-network';
import { MemoryCard } from './memory-card';

export default function MemoryList() {
  // const { data } = useFetchFlowList();
  const { t } = useTranslate('memories');
  const [addOrEditType, setAddOrEditType] = useState<'add' | 'edit'>('add');
  // const [isEdit, setIsEdit] = useState(false);
  const {
    data: list,
    refetch: refetchList,
    isLoading,
  } = useFetchMemoryList({ page: 1, pageSize: 500 });
  const { enabled } = useFeatureFlags();
  const memoSpacetimeEnabled = enabled('memoSpacetime');

  const {
    openCreateModal,
    showMemoryRenameModal,
    hideMemoryModal,
    searchRenameLoading,
    onMemoryRenameOk,
    initialMemory,
  } = useRenameMemory();

  const onMemoryConfirm = (data: ICreateMemoryProps) => {
    onMemoryRenameOk(data, () => {
      refetchList();
    });
  };
  const openCreateModalFun = useCallback(() => {
    // setIsEdit(false);
    setAddOrEditType('add');
    showMemoryRenameModal(defaultMemoryFields as unknown as IMemory);
  }, [showMemoryRenameModal]);
  const [searchUrl, setMemoryUrl] = useSearchParams();
  const isCreate = searchUrl.get('isCreate') === 'true';
  const memoryList = useMemo(
    () => list?.data?.memory_list ?? [],
    [list?.data?.memory_list],
  );
  const hasMemories = memoryList.length > 0;
  const isInitialLoading = isLoading && !list;
  useEffect(() => {
    if (isCreate) {
      openCreateModalFun();
      searchUrl.delete('isCreate');
      setMemoryUrl(searchUrl);
    }
  }, [isCreate, openCreateModalFun, searchUrl, setMemoryUrl]);

  const toolbar = (
    <div className="flex items-center justify-end gap-2">
      <Button size="sm" onClick={() => openCreateModalFun()}>
        <Plus className="size-[1em]" />
        {t('createMemory')}
      </Button>
    </div>
  );

  return (
    <>
      {isInitialLoading ? (
        <article
          className="size-full flex items-center justify-center"
          data-testid="memory-list"
        >
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" />
        </article>
      ) : hasMemories ? (
        <article className="size-full flex flex-col" data-testid="memory-list">
          {memoSpacetimeEnabled ? (
            <MemoSpacetimeNetwork
              memories={memoryList}
              loading={isLoading}
              onCreate={openCreateModalFun}
              toolbar={toolbar}
            />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto px-6 py-5">
              {toolbar}
              <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
                {memoryList.map((memory) => (
                  <MemoryCard
                    key={memory.id}
                    data={memory}
                    showMemoryRenameModal={(value) => {
                      setAddOrEditType('edit');
                      showMemoryRenameModal(value);
                    }}
                  />
                ))}
              </div>
            </div>
          )}
        </article>
      ) : (
        <article
          className="size-full flex items-center justify-center"
          data-testid="memory-list"
        >
          <EmptyAppCard
            showIcon
            size="large"
            className="w-[480px] p-14"
            type={EmptyCardType.Memory}
            onClick={() => openCreateModalFun()}
          />
        </article>
      )}
      {/* {openCreateModal && (
        <RenameDialog
          hideModal={hideMemoryRenameModal}
          onOk={onMemoryRenameConfirm}
          initialName={initialMemoryName}
          loading={searchRenameLoading}
          title={<HomeIcon name="memory" width={'24'} />}
        ></RenameDialog>
      )} */}
      {openCreateModal && (
        <AddOrEditModal
          initialMemory={initialMemory}
          isCreate={addOrEditType === 'add'}
          open={openCreateModal}
          loading={searchRenameLoading}
          onClose={hideMemoryModal}
          onSubmit={onMemoryConfirm}
        />
      )}
    </>
  );
}
