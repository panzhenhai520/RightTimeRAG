import { RAGFlowAvatar } from '@/components/ragflow-avatar';
import { Button } from '@/components/ui/button';
import { useSecondPathName } from '@/hooks/route-hook';
import { cn } from '@/lib/utils';
import { Routes } from '@/routes';
import { formatPureDate } from '@/utils/date';
import { MemoryStick, Settings } from 'lucide-react';
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { getMemoryDisplayName } from '../../memories/utils';
import { useFetchMemoryBaseConfiguration } from '../hooks/use-memory-setting';
import { useHandleMenuClick } from './hooks';

export function SideBar() {
  const pathName = useSecondPathName();
  const { handleMenuClick } = useHandleMenuClick();
  // refreshCount: be for avatar img sync update on top left
  const { data } = useFetchMemoryBaseConfiguration();
  const { t } = useTranslation();
  const displayName = getMemoryDisplayName(data, t);

  const items = useMemo(() => {
    const list = [
      {
        icon: <MemoryStick className="size-4" />,
        label: t(`memory.sideBar.messages`),
        key: Routes.MemoryMessage,
      },
      {
        icon: <Settings className="size-4" />,
        label: t(`memory.sideBar.configuration`),
        key: Routes.MemorySetting,
      },
    ];
    return list;
  }, [t]);

  return (
    <header className="rounded-xl bg-bg-base/70 p-5 shadow-sm ring-1 ring-border-default/20 dark:bg-bg-component/45">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-start gap-4">
          <RAGFlowAvatar
            avatar={data.avatar}
            name={displayName}
            className="size-16 shrink-0"
          />
          <div className="min-w-0 flex-1 space-y-2 text-xs text-text-secondary">
            <h3 className="whitespace-normal break-words text-2xl font-semibold leading-8 text-text-primary">
              {displayName}
            </h3>
            <p className="whitespace-normal break-words text-sm leading-6">
              {data.is_chat_memo ? t('memories.chatMemo') : data.description}
            </p>
            <div>
              {t('knowledgeDetails.created')} {formatPureDate(data.create_time)}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {items.map((item, itemIdx) => {
            const active = '/' + pathName === item.key;
            return (
              <Button
                key={itemIdx}
                variant={active ? 'secondary' : 'ghost'}
                className={cn(
                  'h-9 justify-start gap-2.5 px-3 text-text-secondary',
                  {
                    'bg-bg-card': active,
                    'text-text-primary': active,
                  },
                )}
                onClick={handleMenuClick(item.key)}
              >
                {item.icon}
                <span>{item.label}</span>
              </Button>
            );
          })}
        </div>
      </div>
    </header>
  );
}
