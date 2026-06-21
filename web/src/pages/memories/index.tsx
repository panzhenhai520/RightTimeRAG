import { EmptyCardType } from '@/components/empty/constant';
import { EmptyAppCard } from '@/components/empty/empty';
import ListFilterBar from '@/components/list-filter-bar';
import { Button } from '@/components/ui/button';
import { useTranslate } from '@/hooks/common-hooks';
import { useFeatureFlags } from '@/hooks/use-feature-flags';
import { Plus } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import { AddOrEditModal } from './add-or-edit-modal';
import { defaultMemoryFields } from './constants';
import { useFetchMemoryList, useRenameMemory, useSelectFilters } from './hooks';
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
    searchString,
    handleInputChange,
    refetch: refetchList,
    filterValue,
    handleFilterSubmit,
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
  const { filters } = useSelectFilters();
  const isCreate = searchUrl.get('isCreate') === 'true';
  useEffect(() => {
    if (isCreate) {
      openCreateModalFun();
      searchUrl.delete('isCreate');
      setMemoryUrl(searchUrl);
    }
  }, [isCreate, openCreateModalFun, searchUrl, setMemoryUrl]);

  const toolbar = (
    <ListFilterBar
      className="justify-end gap-0 [&>h1]:hidden [&_[role=toolbar]]:gap-2"
      onSearchChange={handleInputChange}
      searchString={searchString}
      filters={filters}
      onChange={handleFilterSubmit}
      value={filterValue}
    >
      <Button size="sm" onClick={() => openCreateModalFun()}>
        <Plus className="size-[1em]" />
        {t('createMemory')}
      </Button>
    </ListFilterBar>
  );

  return (
    <>
      {list?.data?.memory_list?.length || searchString ? (
        <article className="size-full flex flex-col" data-testid="memory-list">
          {list?.data?.memory_list?.length && memoSpacetimeEnabled ? (
            <MemoSpacetimeNetwork
              memories={list.data.memory_list}
              loading={isLoading}
              onCreate={openCreateModalFun}
              toolbar={toolbar}
            />
          ) : list?.data?.memory_list?.length ? (
            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto px-6 py-5">
              {toolbar}
              <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
                {list.data.memory_list.map((memory) => (
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
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <EmptyAppCard
                showIcon
                size="large"
                className="w-[480px] p-14"
                isSearch
                type={EmptyCardType.Memory}
                onClick={() => openCreateModalFun()}
              />
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
