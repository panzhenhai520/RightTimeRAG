import { MoreButton } from '@/components/more-button';
import { RAGFlowAvatar } from '@/components/ragflow-avatar';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { formatDate } from '@/utils/date';
import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { AddOrEditModal } from '../memories/add-or-edit-modal';
import { useFetchMemoryList, useRenameMemory } from '../memories/hooks';
import { ICreateMemoryProps } from '../memories/interface';
import { MemoryDropdown } from '../memories/memory-dropdown';
import { getMemoryDisplayName } from '../memories/utils';

export function MemoryList({
  setListLength,
  setLoading,
  pageSize,
  displayLimit,
}: {
  setListLength: (length: number) => void;
  setLoading?: (loading: boolean) => void;
  pageSize?: number;
  displayLimit?: number;
}) {
  const { t } = useTranslation();
  const {
    data,
    refetch: refetchList,
    isLoading,
  } = useFetchMemoryList(pageSize ? { page: 1, pageSize } : undefined);
  const { navigateToMemory } = useNavigatePage();
  // const {
  //   openCreateModal,
  //   showSearchRenameModal,
  //   hideSearchRenameModal,
  //   searchRenameLoading,
  //   onSearchRenameOk,
  //   initialSearchName,
  // } = useRenameSearch();
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

  useEffect(() => {
    setListLength(data?.data?.memory_list?.length || 0);
    setLoading?.(isLoading || false);
  }, [data, setListLength, isLoading, setLoading]);
  return (
    <>
      {data?.data.memory_list
        .slice(0, displayLimit ?? pageSize ?? 10)
        .map((x) => {
          const preview = x?.latest_content_preview || x?.description || '';
          return (
            <article
              key={x.id}
              className="group flex h-full cursor-pointer items-start gap-3 overflow-hidden rounded-xl border border-border/60 bg-bg-base/75 p-3 transition hover:border-accent-primary/50 hover:shadow-sm dark:bg-bg-component/45"
              onClick={navigateToMemory(x.id)}
              tabIndex={0}
            >
              <RAGFlowAvatar
                className="size-14 shrink-0 rounded-xl"
                imageClassName="object-cover"
                avatar={x?.avatar}
                name={getMemoryDisplayName(x, t)}
              />
              <div className="flex h-full min-w-0 flex-1 flex-col justify-between">
                <div className="flex min-w-0 items-start justify-between gap-2">
                  <h3 className="min-w-0 flex-1 truncate text-base font-bold leading-snug text-text-primary">
                    {getMemoryDisplayName(x, t)}
                  </h3>
                  <div onClick={(event) => event.stopPropagation()}>
                    <MemoryDropdown
                      memory={x}
                      showMemoryRenameModal={showMemoryRenameModal}
                    >
                      <MoreButton />
                    </MemoryDropdown>
                  </div>
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm text-text-secondary">
                    {preview ||
                      (x?.is_chat_memo
                        ? t('memories.chatMemo')
                        : x?.description)}
                  </div>
                  <div className="mt-1 truncate text-sm text-text-secondary">
                    {formatDate(x?.create_time)}
                  </div>
                </div>
              </div>
            </article>
          );
        })}
      {openCreateModal && (
        <AddOrEditModal
          initialMemory={initialMemory}
          isCreate={false}
          open={openCreateModal}
          loading={searchRenameLoading}
          onClose={hideMemoryModal}
          onSubmit={onMemoryConfirm}
        />
      )}
    </>
  );
}
