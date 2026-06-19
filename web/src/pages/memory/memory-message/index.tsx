import ListFilterBar from '@/components/list-filter-bar';
import { formatDate } from '@/utils/date';
import { t } from 'i18next';
import { getMemoryDisplayName } from '../../memories/utils';
import { useFetchMemoryBaseConfiguration } from '../hooks/use-memory-setting';
import { useFetchMemoryMessageList, useSelectFilters } from './hook';
import { MemoryTable } from './message-table';

function formatMemoPreview(content?: string) {
  return (content || '')
    .replace(/^User Input:\s*/i, '')
    .replace(/\nAgent Response:\s*$/i, '')
    .trim();
}

export default function MemoryMessage() {
  const {
    searchString,
    // documents,
    data,
    pagination,
    handleInputChange,
    setPagination,
    filterValue,
    handleFilterSubmit,
  } = useFetchMemoryMessageList();
  const { data: memory } = useFetchMemoryBaseConfiguration();
  const { filters } = useSelectFilters();
  const memoryTypes = Array.isArray(memory?.memory_type)
    ? memory.memory_type
        .map((type) => t(`memories.${type}`, { defaultValue: type }))
        .join(' / ')
    : '';
  const previewMessages = (data?.messages?.message_list ?? [])
    .map((message) => formatMemoPreview(message.content))
    .filter(Boolean)
    .slice(0, 3);
  const latestForgetAt = data?.messages?.message_list?.[0]?.forget_at;
  const forgetLabel = latestForgetAt
    ? formatDate(latestForgetAt)
    : t('memory.messages.notForgotten');
  return (
    <div className="flex flex-col gap-4">
      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-xl bg-bg-card/60 p-4">
          <div className="text-xs text-text-secondary">
            {t('memories.name')}
          </div>
          <div className="mt-2 whitespace-normal break-words text-base font-semibold leading-6 text-text-primary">
            {getMemoryDisplayName(memory || {}, t)}
          </div>
        </div>
        <div className="rounded-xl bg-bg-card/60 p-4">
          <div className="text-xs text-text-secondary">
            {t('memories.memoryType')}
          </div>
          <div className="mt-2 text-base font-semibold text-text-primary">
            {memoryTypes}
          </div>
        </div>
        <div className="rounded-xl bg-bg-card/60 p-4">
          <div className="text-xs text-text-secondary">
            {t('memory.sideBar.messages')}
          </div>
          <div className="mt-2 text-base font-semibold text-text-primary">
            {data?.messages?.total_count ?? 0}
          </div>
        </div>
        <div className="rounded-xl bg-bg-card/60 p-4">
          <div className="text-xs text-text-secondary">
            {t('memory.messages.forgetStatus', {
              defaultValue: t('memory.messages.forgetAt'),
            })}
          </div>
          <div className="mt-2 truncate text-base font-semibold text-text-primary">
            {forgetLabel}
          </div>
        </div>
        <div className="rounded-xl bg-bg-card/60 p-4">
          <div className="text-xs text-text-secondary">
            {t('knowledgeDetails.created')}
          </div>
          <div className="mt-2 text-base font-semibold text-text-primary">
            {memory?.create_time ? formatDate(memory.create_time) : '-'}
          </div>
        </div>
      </section>
      {previewMessages.length > 0 && (
        <section className="grid gap-3 xl:grid-cols-2">
          {previewMessages.map((content, index) => (
            <article
              key={`${index}-${content.slice(0, 24)}`}
              className="min-h-[150px] rounded-xl bg-bg-card/55 p-4"
            >
              <div className="mb-2 text-xs font-medium text-text-secondary">
                {t('memory.messages.content')}
              </div>
              <div className="line-clamp-8 whitespace-pre-line break-words text-xs leading-5 text-text-primary">
                {content}
              </div>
            </article>
          ))}
        </section>
      )}
      {previewMessages.length === 0 && (
        <section className="rounded-xl bg-bg-card/55 p-5">
          <div className="text-base font-semibold text-text-primary">
            {t('memory.messages.emptyMemoTitle')}
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
            {t('memory.messages.emptyMemoDescription')}
          </p>
        </section>
      )}
      <ListFilterBar
        title={t('header.dataset')}
        onSearchChange={handleInputChange}
        searchString={searchString}
        // showFilter={false}
        // value={filterValue}
        // onChange={handleFilterSubmit}
        // onOpenChange={onOpenChange}
        // filters={filters}
        filters={filters}
        onChange={handleFilterSubmit}
        value={filterValue}
        leftPanel={
          <div className="items-start">
            <div className="pb-1">{t('memory.sideBar.messages')}</div>
            <div className="text-text-secondary text-sm font-normal">
              {t('memory.messages.messageDescription')}
            </div>
          </div>
        }
      ></ListFilterBar>
      <MemoryTable
        messages={data?.messages?.message_list ?? []}
        pagination={pagination}
        setPagination={setPagination}
        total={data?.messages?.total_count ?? 0}
        // rowSelection={rowSelection}
        // setRowSelection={setRowSelection}
        // loading={loading}
      ></MemoryTable>
    </div>
  );
}
