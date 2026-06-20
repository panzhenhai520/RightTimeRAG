import type { TFunction } from 'i18next';
import { IMemory } from './interface';

function cleanChatMemoTitle(title?: string) {
  return (title || '')
    .replace(
      /^(我们注意到用户的问题是关于|我们注意到|我注意到|用户的问题是关于|这个问题是关于|The user asks about|This question is about)\s*[:：，,]*\s*/i,
      '',
    )
    .trim();
}

export function getMemoryDisplayName(memory: Partial<IMemory>, t: TFunction) {
  const structuredTitle = cleanChatMemoTitle(
    memory.structured_summary?.display_title,
  );
  if (structuredTitle) {
    return structuredTitle;
  }

  if (memory.is_chat_memo) {
    return (
      cleanChatMemoTitle(memory.display_name) ||
      cleanChatMemoTitle(memory.description) ||
      t('memories.chatMemo')
    );
  }

  return memory.display_name || memory.name || t('memories.memory');
}
