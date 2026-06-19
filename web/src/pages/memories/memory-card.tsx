import { HomeCard } from '@/components/home-card';
import { MoreButton } from '@/components/more-button';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
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

  return (
    <HomeCard
      data={{
        name: displayName,
        avatar: data?.avatar,
        description: data?.is_chat_memo ? '' : data?.description,
        update_time: data?.create_time,
      }}
      moreDropdown={
        <MemoryDropdown
          memory={data}
          showMemoryRenameModal={showMemoryRenameModal}
        >
          <MoreButton></MoreButton>
        </MemoryDropdown>
      }
      onClick={navigateToMemory(data?.id)}
    />
  );
}
