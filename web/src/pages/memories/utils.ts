import type { TFunction } from 'i18next';
import { IMemory } from './interface';

export function getMemoryDisplayName(memory: Partial<IMemory>, t: TFunction) {
  if (memory.is_chat_memo) {
    return (
      memory.display_name ||
      memory.description?.trim() ||
      t('memories.chatMemo')
    );
  }

  return memory.display_name || memory.name || t('memories.memory');
}
