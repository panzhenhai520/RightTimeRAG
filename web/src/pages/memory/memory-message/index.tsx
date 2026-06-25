import ListFilterBar from '@/components/list-filter-bar';
import { Button } from '@/components/ui/button';
import { formatDate } from '@/utils/date';
import { t } from 'i18next';
import { Download } from 'lucide-react';
import { useCallback } from 'react';
import { getMemoryDisplayName } from '../../memories/utils';
import { useFetchMemoryBaseConfiguration } from '../hooks/use-memory-setting';
import { useFetchMemoryMessageList, useSelectFilters } from './hook';
import { IMessageInfo } from './interface';
import { MemoryTable } from './message-table';

function stripProcessBlocks(text: string): string {
  return (text || '')
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/<retrieving>[\s\S]*?<\/retrieving>/gi, '')
    .trim();
}

function exportAsMarkdown(messages: IMessageInfo[], memoryName: string): void {
  const lines: string[] = [`# ${memoryName}`, ''];
  for (const msg of messages) {
    const content = stripProcessBlocks(msg.content || '');
    if (!content) continue;
    const ts = msg.valid_at || '';
    const typeLabel =
      msg.message_type === 'raw'
        ? '用户/原始'
        : msg.message_type === 'semantic'
          ? '语义记忆'
          : msg.message_type === 'procedural'
            ? '流程摘要'
            : msg.message_type;
    lines.push(`## [${typeLabel}] ${ts}`);
    lines.push('');
    lines.push(content);
    lines.push('');
    lines.push('---');
    lines.push('');
  }
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${memoryName || 'memory'}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

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
  const memoryDisplayName = getMemoryDisplayName(memory || {}, t);
  const handleExport = useCallback(() => {
    exportAsMarkdown(data?.messages?.message_list ?? [], memoryDisplayName);
  }, [data?.messages?.message_list, memoryDisplayName]);
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
            {memoryDisplayName}
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
        filters={filters}
        onChange={handleFilterSubmit}
        value={filterValue}
        leftPanel={
          <div className="flex items-center justify-between gap-4 w-full">
            <div className="items-start">
              <div className="pb-1">{t('memory.sideBar.messages')}</div>
              <div className="text-text-secondary text-sm font-normal">
                {t('memory.messages.messageDescription')}
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              className="shrink-0"
            >
              <Download className="size-3.5" />
              导出 Markdown
            </Button>
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
