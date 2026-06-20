import {
  extractTopicKeywords,
  getMemoryTopicText,
  inferCanonicalTopic,
} from './canonical-topic';
import type { IMemory } from './interface';

export type MemoProfileSourceKind = 'chat' | 'search' | 'agent' | 'memory';

export interface MemoProfileInput {
  memoryId: string;
  topicId: string;
  topicLabel: string;
  displayTitle: string;
  aliases: string[];
  keywords: string[];
  createdAt: number;
  turns: number;
  summary: string;
  sourceKind: MemoProfileSourceKind;
  assistantId?: string;
  sessionId?: string;
  ownerName?: string;
  relatedKbIds: string[];
}

function parseCreateTime(memory: Partial<IMemory>) {
  if (memory.create_time) {
    const timestamp =
      memory.create_time > 10_000_000_000
        ? memory.create_time
        : memory.create_time * 1000;
    if (Number.isFinite(timestamp)) return timestamp;
  }

  if (memory.create_date) {
    const parsed = new Date(memory.create_date).getTime();
    if (!Number.isNaN(parsed)) return parsed;
  }

  return Date.now();
}

function getDisplayTitle(memory: Partial<IMemory>) {
  return (
    memory.structured_summary?.display_title ||
    memory.display_name ||
    memory.description ||
    memory.name ||
    'memo'
  );
}

function inferSourceKind(memory: Partial<IMemory>): MemoProfileSourceKind {
  if (!memory.is_chat_memo) return 'memory';
  const agentId = String(memory.latest_agent_id || '');
  if (agentId.startsWith('search-')) return 'search';
  if (agentId.startsWith('canvas-') || agentId.startsWith('agent-')) {
    return 'agent';
  }
  return 'chat';
}

export function buildMemoProfileInput(memory: IMemory): MemoProfileInput {
  const displayTitle = getDisplayTitle(memory);
  const textForTopic = getMemoryTopicText(memory, displayTitle);
  const canonicalTopic = inferCanonicalTopic(textForTopic || displayTitle);
  const structuredAliases = memory.structured_summary?.aliases ?? [];
  const keywords = Array.from(
    new Set([
      ...extractTopicKeywords(textForTopic || displayTitle, 12),
      ...structuredAliases.map((alias) => alias.toLowerCase()),
      ...canonicalTopic.aliases.map((alias) => alias.toLowerCase()),
    ]),
  ).slice(0, 16);

  return {
    memoryId: memory.id,
    topicId: canonicalTopic.id,
    topicLabel: canonicalTopic.label || displayTitle,
    displayTitle,
    aliases: Array.from(
      new Set(
        [...structuredAliases, ...canonicalTopic.aliases].filter(Boolean),
      ),
    ),
    keywords,
    createdAt: parseCreateTime(memory),
    turns: Math.max(1, Number(memory.message_count || 1)),
    summary:
      memory.latest_content_preview ||
      memory.structured_summary?.facts?.map((fact) => fact.text).join('\n') ||
      memory.description ||
      '',
    sourceKind: inferSourceKind(memory),
    assistantId: memory.latest_agent_id,
    sessionId: memory.latest_session_id,
    ownerName: memory.owner_name,
    relatedKbIds: memory.structured_summary?.related_kb_ids ?? [],
  };
}

export function buildMemoProfileInputs(memories: IMemory[]) {
  return memories.map(buildMemoProfileInput);
}
