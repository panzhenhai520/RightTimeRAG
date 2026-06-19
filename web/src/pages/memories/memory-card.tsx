import { MoreButton } from '@/components/more-button';
import { RAGFlowAvatar } from '@/components/ragflow-avatar';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { formatDate } from '@/utils/date';
import { MemoryStick } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { IMemory } from './interface';
import { MemoryDropdown } from './memory-dropdown';
import { getMemoryDisplayName } from './utils';

interface IProps {
  data: IMemory;
  showMemoryRenameModal: (data: IMemory) => void;
}
export function MemoryCard({ data, showMemoryRenameModal }: IProps) {
  const { navigateToMemory } = useNavigatePage();
  const { t } = useTranslation();
  const displayName = getMemoryDisplayName(data, t);
  const typeLabel = Array.isArray(data?.memory_type)
    ? data.memory_type
        .map((type) => t(`memories.${type}`, { defaultValue: type }))
        .join(' / ')
    : '';
  const description = data?.is_chat_memo
    ? t('memories.chatMemo')
    : data?.description;
  const preview = data?.latest_content_preview || data?.description || '';
  const forgetLabel = data?.latest_forget_at
    ? formatDate(data.latest_forget_at)
    : t('memory.messages.notForgotten');

  return (
    <article
      className="group flex h-[300px] cursor-pointer flex-col rounded-xl border border-border/60 bg-bg-base/80 p-5 shadow-sm transition hover:border-accent-primary/50 hover:shadow-md dark:bg-bg-component/45"
      onClick={navigateToMemory(data?.id)}
      tabIndex={0}
      data-testid="memory-card"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <RAGFlowAvatar
            className="size-14 shrink-0 rounded-xl"
            avatar={data?.avatar}
            name={displayName}
          />
          <div className="min-w-0">
            <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-accent-primary/10 px-2 py-1 text-xs font-medium text-accent-primary">
              <MemoryStick className="size-3.5" />
              {description}
            </div>
            <h3 className="line-clamp-3 whitespace-normal break-words text-base font-semibold leading-6 text-text-primary">
              {displayName}
            </h3>
          </div>
        </div>
        <div onClick={(event) => event.stopPropagation()}>
          <MemoryDropdown
            memory={data}
            showMemoryRenameModal={showMemoryRenameModal}
          >
            <MoreButton />
          </MemoryDropdown>
        </div>
      </div>

      {preview && (
        <p className="mt-4 line-clamp-5 whitespace-pre-line break-words text-xs leading-5 text-text-secondary">
          {preview}
        </p>
      )}

      <div className="mt-auto grid grid-cols-2 gap-2 pt-4 text-[11px] leading-4 text-text-secondary">
        {[
          [t('memory.sideBar.messages'), data?.message_count ?? 0],
          [t('memories.memoryType'), typeLabel],
          [t('memory.config.storageType'), data?.storage_type],
          [
            t('memory.messages.forgetStatus', {
              defaultValue: t('memory.messages.forgetAt'),
            }),
            forgetLabel,
          ],
          [t('knowledgeDetails.created'), formatDate(data?.create_time)],
        ].map(([label, value]) => (
          <div
            key={String(label)}
            className="min-w-0 rounded-lg bg-bg-card/60 px-3 py-2"
          >
            <div className="truncate">{label}</div>
            <div className="mt-0.5 truncate font-medium text-text-primary">
              {value}
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}
