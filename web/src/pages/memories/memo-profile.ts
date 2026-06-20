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

export interface MemoTopicMetric {
  topicId: string;
  topicLabel: string;
  memoryIds: string[];
  aliases: string[];
  keywords: string[];
  relatedKbIds: string[];
  sourceKinds: MemoProfileSourceKind[];
  memoCount: number;
  turnCount: number;
  frequency: number;
  activeDays: number;
  firstSeen: number;
  lastSeen: number;
  centrality: number;
  connectedTopicIds: string[];
}

export interface MemoTopicEdge {
  sourceTopicId: string;
  targetTopicId: string;
  weight: number;
  sharedSignals: string[];
}

export interface MemoProfileMetrics {
  topics: MemoTopicMetric[];
  edges: MemoTopicEdge[];
  connectionDensity: number;
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

function unique<T>(values: T[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function dayKey(timestamp: number) {
  const date = new Date(timestamp);
  return `${date.getFullYear()}-${date.getMonth() + 1}-${date.getDate()}`;
}

function overlap(a: string[], b: string[]) {
  const bSet = new Set(b.map((item) => item.toLowerCase()));
  return unique(
    a.map((item) => item.toLowerCase()).filter((item) => bSet.has(item)),
  );
}

function buildTopicSignalSet(topic: MemoTopicMetric) {
  return unique([
    ...topic.aliases,
    ...topic.keywords,
    ...topic.relatedKbIds.map((kbId) => `kb:${kbId}`),
  ]);
}

function buildTopicEdges(topics: MemoTopicMetric[]) {
  const edges: MemoTopicEdge[] = [];
  for (let i = 0; i < topics.length; i += 1) {
    for (let j = i + 1; j < topics.length; j += 1) {
      const sharedSignals = overlap(
        buildTopicSignalSet(topics[i]),
        buildTopicSignalSet(topics[j]),
      );
      if (sharedSignals.length === 0) continue;
      edges.push({
        sourceTopicId: topics[i].topicId,
        targetTopicId: topics[j].topicId,
        weight: sharedSignals.length,
        sharedSignals,
      });
    }
  }
  return edges;
}

export function buildMemoProfileMetrics(
  inputs: MemoProfileInput[],
): MemoProfileMetrics {
  const totalMemos = Math.max(1, inputs.length);
  const grouped = new Map<string, MemoProfileInput[]>();
  inputs.forEach((input) => {
    grouped.set(input.topicId, [...(grouped.get(input.topicId) ?? []), input]);
  });

  const topics = Array.from(grouped.entries()).map(([topicId, items]) => {
    const sorted = [...items].sort((a, b) => a.createdAt - b.createdAt);
    const activeDays = unique(sorted.map((item) => dayKey(item.createdAt)));
    return {
      topicId,
      topicLabel: sorted.at(-1)?.topicLabel || topicId,
      memoryIds: unique(sorted.map((item) => item.memoryId)),
      aliases: unique(sorted.flatMap((item) => item.aliases)),
      keywords: unique(sorted.flatMap((item) => item.keywords)),
      relatedKbIds: unique(sorted.flatMap((item) => item.relatedKbIds)),
      sourceKinds: unique(sorted.map((item) => item.sourceKind)),
      memoCount: sorted.length,
      turnCount: sorted.reduce((total, item) => total + item.turns, 0),
      frequency: sorted.length / totalMemos,
      activeDays: activeDays.length,
      firstSeen: sorted[0]?.createdAt ?? 0,
      lastSeen: sorted.at(-1)?.createdAt ?? 0,
      centrality: 0,
      connectedTopicIds: [],
    } satisfies MemoTopicMetric;
  });

  const edges = buildTopicEdges(topics);
  const connectionMap = new Map<string, Set<string>>();
  edges.forEach((edge) => {
    connectionMap.set(
      edge.sourceTopicId,
      connectionMap.get(edge.sourceTopicId) ?? new Set(),
    );
    connectionMap.set(
      edge.targetTopicId,
      connectionMap.get(edge.targetTopicId) ?? new Set(),
    );
    connectionMap.get(edge.sourceTopicId)?.add(edge.targetTopicId);
    connectionMap.get(edge.targetTopicId)?.add(edge.sourceTopicId);
  });

  const maxConnections = Math.max(1, topics.length - 1);
  const enrichedTopics = topics
    .map((topic) => {
      const connectedTopicIds = Array.from(
        connectionMap.get(topic.topicId) ?? [],
      );
      return {
        ...topic,
        connectedTopicIds,
        centrality: connectedTopicIds.length / maxConnections,
      };
    })
    .sort((a, b) => {
      if (b.memoCount !== a.memoCount) return b.memoCount - a.memoCount;
      if (b.turnCount !== a.turnCount) return b.turnCount - a.turnCount;
      return b.lastSeen - a.lastSeen;
    });

  const possibleEdges = (topics.length * (topics.length - 1)) / 2;
  return {
    topics: enrichedTopics,
    edges,
    connectionDensity: possibleEdges > 0 ? edges.length / possibleEdges : 0,
  };
}
