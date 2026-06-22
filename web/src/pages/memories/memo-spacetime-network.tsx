import { Button } from '@/components/ui/button';
import { DEV_FEATURE_SESSION_KEY, Routes } from '@/routes';
import { formatDate } from '@/utils/date';
import {
  BrainCircuit,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  GitBranch,
  Loader2,
  LocateFixed,
  MessageSquareText,
  MousePointer2,
  Network,
  RotateCcw,
  Share2,
  SkipBack,
  SkipForward,
} from 'lucide-react';
import {
  MouseEvent as ReactMouseEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import {
  extractTopicKeywords,
  getCanonicalTopicFromMemory,
  getMemoryTopicText,
} from './canonical-topic';
import { IMemory } from './interface';
import { getMemoryDisplayName } from './utils';

type MemoCategory = 'raw' | 'semantic' | 'episodic' | 'procedural' | 'memo';

type MemoSpacetimeNode = {
  id: string;
  topicId: string;
  primaryMemoryId: string;
  memoryIds: string[];
  memoryCount: number;
  topic: string;
  sourceTopics: string[];
  aliases: string[];
  preview: string;
  summary: string;
  keywords: string[];
  category: MemoCategory;
  createdAt: Date;
  turns: number;
  assistantId?: string;
  assistantName?: string;
  userId?: string;
  language?: string;
  ownerName?: string;
  storageType?: string;
  memoryTypeLabel: string;
  forgetLabel: string;
};

type PositionedNode = MemoSpacetimeNode & {
  x: number;
  y: number;
  radius: number;
  visible: boolean;
};

type CurveControl =
  | {
      kind: 'quadratic';
      cp: { x: number; y: number };
    }
  | {
      kind: 'bezier';
      cp1: { x: number; y: number };
      cp2: { x: number; y: number };
    };

type MemoRelationType = 'sharedTopic' | 'sharedKeywords' | 'crossLanguageTopic';

type PositionedRelation = {
  id: string;
  source: PositionedNode;
  target: PositionedNode;
  sharedKeywords: string[];
  relationType: MemoRelationType;
  strength: number;
  curve: CurveControl;
};

type DateFocusReport = {
  dateLabel: string;
  nodeCount: number;
  turnCount: number;
  categories: string[];
  timeRange: string;
  hasNodes: boolean;
};

type KeywordWeaveReport = {
  topKeyword: string;
  topKeywords: Array<[string, number]>;
  connectedCount: number;
  daySpan: number;
  primaryTopic: string;
};

type CanvasTheme = {
  background: string;
  panel: string;
  dayEven: string;
  dayOdd: string;
  grid: string;
  gridStrong: string;
  text: string;
  muted: string;
  accent: string;
  edge: string;
  nodeStroke: string;
  activeStroke: string;
};

const CATEGORY_COLORS: Record<MemoCategory, string> = {
  raw: '#9b6b55',
  semantic: '#4d7fa4',
  episodic: '#b78b45',
  procedural: '#7d6fb0',
  memo: '#7c4f63',
};

const KEYWORD_COLOR_PALETTE = [
  '#3b82f6',
  '#10b981',
  '#f59e0b',
  '#8b5cf6',
  '#f43f5e',
  '#14b8a6',
  '#ec4899',
  '#84cc16',
  '#6366f1',
  '#ef4444',
];

const KEYWORD_COLOR_HINTS = [
  {
    keywords: ['传承', 'succession', '继承', '接班'],
    color: '#3b82f6',
  },
  {
    keywords: ['治理', 'governance', '董事会', '章程'],
    color: '#10b981',
  },
  {
    keywords: ['家族企业', 'family business', '企业经营', 'enterprise'],
    color: '#f59e0b',
  },
  {
    keywords: ['信托', 'trust', '财富', 'wealth'],
    color: '#8b5cf6',
  },
  {
    keywords: ['二代', 'next generation', '教育', '培养'],
    color: '#f43f5e',
  },
  {
    keywords: ['慈善', 'charity', '公益', 'philanthropy'],
    color: '#14b8a6',
  },
];

const VISIBLE_DAYS = 7;
const HALF_VISIBLE_DAYS = Math.floor(VISIBLE_DAYS / 2);
const ONE_DAY_MS = 86_400_000;
const PLOT_MARGINS = { left: 76, top: 58, right: 28, bottom: 44 };

type TimeDomain = {
  startMinute: number;
  endMinute: number;
  tickStep: number;
};

type PlotBox = {
  left: number;
  top: number;
  right: number;
  bottom: number;
  plotWidth: number;
  plotHeight: number;
};

function getFirstMemoryType(memory: IMemory): MemoCategory {
  const memoryType = Array.isArray(memory.memory_type)
    ? memory.memory_type[0]
    : undefined;

  if (memory.is_chat_memo) return 'memo';
  if (
    memoryType === 'raw' ||
    memoryType === 'semantic' ||
    memoryType === 'episodic' ||
    memoryType === 'procedural'
  ) {
    return memoryType;
  }

  return 'memo';
}

function parseCreateTime(memory: IMemory) {
  if (memory.create_time) {
    const timestamp =
      memory.create_time > 10_000_000_000
        ? memory.create_time
        : memory.create_time * 1000;
    const parsed = new Date(timestamp);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }

  if (memory.create_date) {
    const parsed = new Date(memory.create_date);
    if (!Number.isNaN(parsed.getTime())) return parsed;
  }

  return new Date();
}

function buildNode(memory: IMemory, t: ReturnType<typeof useTranslation>['t']) {
  const topic = getMemoryDisplayName(memory, t);
  const preview = memory.latest_content_preview || memory.description || '';
  const textForKeywords = getMemoryTopicText(memory, topic);
  const canonicalTopic = getCanonicalTopicFromMemory(
    memory,
    textForKeywords || topic,
  );
  const structuredTitle = memory.structured_summary?.display_title;
  const structuredAliases = memory.structured_summary?.aliases ?? [];
  const keywords = Array.from(
    new Set([
      ...extractTopicKeywords(textForKeywords || topic),
      ...structuredAliases.map((alias) => alias.toLowerCase()),
      ...canonicalTopic.aliases.map((alias) => alias.toLowerCase()),
    ]),
  ).slice(0, 12);
  const category = getFirstMemoryType(memory);
  const memoryTypes = Array.isArray(memory.memory_type)
    ? memory.memory_type
        .map((type) => t(`memories.${type}`, { defaultValue: type }))
        .join(' / ')
    : '';

  return {
    id: canonicalTopic.id,
    topicId: canonicalTopic.id,
    primaryMemoryId: memory.id,
    memoryIds: [memory.id],
    memoryCount: 1,
    topic: structuredTitle || topic || canonicalTopic.label,
    sourceTopics: [topic],
    aliases: keywords,
    preview,
    summary: preview,
    keywords,
    category,
    createdAt: parseCreateTime(memory),
    turns: Math.max(1, Number(memory.message_count || 1)),
    language: canonicalTopic.language,
    ownerName: memory.owner_name,
    storageType: memory.storage_type,
    memoryTypeLabel: memory.is_chat_memo
      ? t('memories.chatMemo')
      : memoryTypes || t('memories.memory'),
    forgetLabel: memory.latest_forget_at
      ? formatDate(memory.latest_forget_at)
      : t('memory.messages.notForgotten'),
  };
}

function mergeList(a: string[], b: string[], limit = 16) {
  return Array.from(new Set([...a, ...b].filter(Boolean))).slice(0, limit);
}

function groupCanonicalNodes(nodes: MemoSpacetimeNode[]) {
  const grouped = new Map<string, MemoSpacetimeNode>();
  nodes.forEach((node) => {
    const existing = grouped.get(node.topicId);
    if (!existing) {
      grouped.set(node.topicId, node);
      return;
    }

    const isNewer = node.createdAt.getTime() > existing.createdAt.getTime();
    grouped.set(node.topicId, {
      ...existing,
      primaryMemoryId: isNewer
        ? node.primaryMemoryId
        : existing.primaryMemoryId,
      memoryIds: mergeList(existing.memoryIds, node.memoryIds, 100),
      memoryCount: existing.memoryCount + node.memoryCount,
      sourceTopics: mergeList(existing.sourceTopics, node.sourceTopics, 12),
      aliases: mergeList(existing.aliases, node.aliases, 18),
      keywords: mergeList(existing.keywords, node.keywords, 18),
      preview: mergeList(
        existing.preview ? [existing.preview] : [],
        node.preview ? [node.preview] : [],
        3,
      ).join('\n\n'),
      summary: mergeList(
        existing.summary ? [existing.summary] : [],
        node.summary ? [node.summary] : [],
        3,
      ).join('\n\n'),
      createdAt: isNewer ? node.createdAt : existing.createdAt,
      turns: existing.turns + node.turns,
      forgetLabel: isNewer ? node.forgetLabel : existing.forgetLabel,
    });
  });

  return Array.from(grouped.values()).sort(
    (a, b) => b.createdAt.getTime() - a.createdAt.getTime(),
  );
}

function getCanvasTheme(): CanvasTheme {
  const styles = getComputedStyle(document.documentElement);
  const accent = styles.getPropertyValue('--accent-primary').trim();
  const isDark = document.documentElement.classList.contains('dark');
  const accentColor = accent
    ? `rgb(${accent})`
    : isDark
      ? '#7c8cff'
      : '#8d4660';

  if (!isDark) {
    return {
      background: '#fbf7f5',
      panel: 'rgba(255,255,255,0.72)',
      dayEven: 'rgba(255,255,255,0.24)',
      dayOdd: 'rgba(141,70,96,0.04)',
      grid: 'rgba(118,90,82,0.16)',
      gridStrong: 'rgba(141,70,96,0.34)',
      text: 'rgba(40,49,62,0.86)',
      muted: 'rgba(98,104,116,0.66)',
      accent: accentColor,
      edge: 'rgba(118,90,101,0.13)',
      nodeStroke: 'rgba(255,255,255,0.88)',
      activeStroke: '#6d334a',
    };
  }

  return {
    background: '#070b14',
    panel: 'rgba(15,23,42,0.36)',
    dayEven: 'rgba(51,65,85,0.22)',
    dayOdd: 'rgba(30,41,59,0.28)',
    grid: 'rgba(71,85,105,0.34)',
    gridStrong: 'rgba(99,102,241,0.38)',
    text: 'rgba(226,232,240,0.9)',
    muted: 'rgba(148,163,184,0.72)',
    accent: accentColor,
    edge: 'rgba(148,163,184,0.09)',
    nodeStroke: 'rgba(255,255,255,0.68)',
    activeStroke: '#e0e7ff',
  };
}

function hashString(value: string) {
  return value.split('').reduce((hash, char) => {
    return (hash << 5) - hash + char.charCodeAt(0);
  }, 0);
}

function getKeywordColor(keyword?: string) {
  const normalized = (keyword || '').trim().toLowerCase();
  if (!normalized) return KEYWORD_COLOR_PALETTE[0];

  const hinted = KEYWORD_COLOR_HINTS.find((hint) =>
    hint.keywords.some((item) => normalized.includes(item.toLowerCase())),
  );
  if (hinted) return hinted.color;

  return KEYWORD_COLOR_PALETTE[
    Math.abs(hashString(normalized)) % KEYWORD_COLOR_PALETTE.length
  ];
}

function getNodePrimaryKeyword(node: MemoSpacetimeNode) {
  return node.keywords[0] || node.topic || node.memoryTypeLabel;
}

function getNodeColor(node: MemoSpacetimeNode) {
  return getKeywordColor(getNodePrimaryKeyword(node));
}

function sharedKeywordCount(a: MemoSpacetimeNode, b: MemoSpacetimeNode) {
  return getSharedKeywords(a, b).length;
}

const LINK_STOP_KEYWORDS = new Set([
  '家族',
  'family',
  '企业',
  'business',
  'office',
  'memory',
  'memo',
]);

function getLinkKeywords(node: MemoSpacetimeNode) {
  return node.keywords.filter((keyword) => {
    const normalized = keyword.trim().toLowerCase();
    return normalized.length > 1 && !LINK_STOP_KEYWORDS.has(normalized);
  });
}

function getSharedKeywords(a: MemoSpacetimeNode, b: MemoSpacetimeNode) {
  const bKeywords = new Set(getLinkKeywords(b));
  return getLinkKeywords(a).filter((keyword) => bKeywords.has(keyword));
}

function normalizeSignal(value?: string) {
  return (value || '').trim().toLowerCase();
}

function getRelationType(
  source: MemoSpacetimeNode,
  target: MemoSpacetimeNode,
  sharedKeywords: string[],
): MemoRelationType {
  const primarySignals = new Set([
    normalizeSignal(getNodePrimaryKeyword(source)),
    normalizeSignal(getNodePrimaryKeyword(target)),
    normalizeSignal(source.topic),
    normalizeSignal(target.topic),
  ]);
  const hasPrimarySignal = sharedKeywords.some((keyword) =>
    primarySignals.has(normalizeSignal(keyword)),
  );

  if (hasPrimarySignal) return 'sharedTopic';
  if (
    source.language &&
    target.language &&
    source.language !== target.language
  ) {
    return 'crossLanguageTopic';
  }

  return 'sharedKeywords';
}

function getRelationStrength(
  sharedKeywords: string[],
  source: MemoSpacetimeNode,
  target: MemoSpacetimeNode,
) {
  const keywordWeight = Math.min(0.42, sharedKeywords.length * 0.12);
  const turnWeight = Math.min(
    0.16,
    Math.sqrt(source.turns + target.turns) * 0.025,
  );
  const memoryWeight = Math.min(
    0.12,
    Math.sqrt(source.memoryCount + target.memoryCount) * 0.025,
  );
  return Math.round(
    Math.min(0.94, 0.3 + keywordWeight + turnWeight + memoryWeight) * 100,
  );
}

function getRelationCurve(
  source: PositionedNode,
  target: PositionedNode,
  dayWidth: number,
): CurveControl {
  if (Math.abs(source.x - target.x) < 2) {
    const midY = (source.y + target.y) / 2;
    const offset = -Math.min(
      dayWidth * 0.45,
      Math.abs(source.y - target.y) * 0.35,
    );
    return {
      kind: 'quadratic',
      cp: { x: source.x + offset, y: midY },
    };
  }

  const midX = (source.x + target.x) / 2;
  return {
    kind: 'bezier',
    cp1: { x: midX, y: source.y },
    cp2: { x: midX, y: target.y },
  };
}

function buildVisibleRelations(positioned: PositionedNode[], dayWidth: number) {
  const relations: PositionedRelation[] = [];

  positioned.forEach((source, sourceIndex) => {
    if (!source.visible) return;
    positioned.slice(sourceIndex + 1).forEach((target) => {
      if (!target.visible) return;
      const sharedKeywords = getSharedKeywords(source, target);
      if (!sharedKeywords.length) return;
      relations.push({
        id: [source.id, target.id].sort().join('__'),
        source,
        target,
        sharedKeywords,
        relationType: getRelationType(source, target, sharedKeywords),
        strength: getRelationStrength(sharedKeywords, source, target),
        curve: getRelationCurve(source, target, dayWidth),
      });
    });
  });

  return relations;
}

function traceRelationPath(
  ctx: CanvasRenderingContext2D,
  relation: PositionedRelation,
) {
  ctx.beginPath();
  ctx.moveTo(relation.source.x, relation.source.y);
  if (relation.curve.kind === 'quadratic') {
    ctx.quadraticCurveTo(
      relation.curve.cp.x,
      relation.curve.cp.y,
      relation.target.x,
      relation.target.y,
    );
  } else {
    ctx.bezierCurveTo(
      relation.curve.cp1.x,
      relation.curve.cp1.y,
      relation.curve.cp2.x,
      relation.curve.cp2.y,
      relation.target.x,
      relation.target.y,
    );
  }
}

function getRelationPoint(relation: PositionedRelation, progress: number) {
  const t = Math.max(0, Math.min(1, progress));
  const x0 = relation.source.x;
  const y0 = relation.source.y;
  const x3 = relation.target.x;
  const y3 = relation.target.y;

  if (relation.curve.kind === 'quadratic') {
    const { x: x1, y: y1 } = relation.curve.cp;
    const oneMinusT = 1 - t;
    return {
      x: oneMinusT * oneMinusT * x0 + 2 * oneMinusT * t * x1 + t * t * x3,
      y: oneMinusT * oneMinusT * y0 + 2 * oneMinusT * t * y1 + t * t * y3,
    };
  }

  const { x: x1, y: y1 } = relation.curve.cp1;
  const { x: x2, y: y2 } = relation.curve.cp2;
  const oneMinusT = 1 - t;
  return {
    x:
      oneMinusT * oneMinusT * oneMinusT * x0 +
      3 * oneMinusT * oneMinusT * t * x1 +
      3 * oneMinusT * t * t * x2 +
      t * t * t * x3,
    y:
      oneMinusT * oneMinusT * oneMinusT * y0 +
      3 * oneMinusT * oneMinusT * t * y1 +
      3 * oneMinusT * t * t * y2 +
      t * t * t * y3,
  };
}

function findNearestRelation(
  x: number,
  y: number,
  relations: PositionedRelation[],
) {
  let nearest:
    | {
        relation: PositionedRelation;
        distance: number;
      }
    | undefined;

  relations.forEach((relation) => {
    for (let index = 0; index <= 36; index += 1) {
      const point = getRelationPoint(relation, index / 36);
      const distance = Math.hypot(point.x - x, point.y - y);
      if (!nearest || distance < nearest.distance) {
        nearest = { relation, distance };
      }
    }
  });

  return nearest && nearest.distance <= 18 ? nearest.relation : undefined;
}

function formatDay(date: Date) {
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function formatDayWithWeekday(date: Date, language?: string) {
  return new Intl.DateTimeFormat(language || undefined, {
    month: 'numeric',
    day: 'numeric',
    weekday: 'short',
  }).format(date);
}

function formatTime(date: Date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatMinuteLabel(minute: number) {
  if (minute >= 1440) return '24:00';
  const normalized = Math.max(0, Math.min(1440, minute));
  const hour = Math.floor(normalized / 60) % 24;
  const minutes = normalized % 60;
  return `${String(hour).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
}

function getStartOfDay(date: Date) {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function addDays(date: Date, days: number) {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}

function formatInputDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function isSameDay(a: Date, b: Date) {
  return getStartOfDay(a).getTime() === getStartOfDay(b).getTime();
}

function getVisibleCenterDate(offsetDays: number) {
  const date = getStartOfDay(new Date());
  date.setDate(date.getDate() + Math.round(offsetDays));
  return date;
}

function getVisibleStartDate(centerDate: Date) {
  return addDays(centerDate, -HALF_VISIBLE_DAYS);
}

function getAdaptiveTimeDomain(
  nodes: MemoSpacetimeNode[],
  centerDate: Date,
): TimeDomain {
  const startDay = addDays(centerDate, -HALF_VISIBLE_DAYS).getTime();
  const endDay = addDays(centerDate, HALF_VISIBLE_DAYS).getTime();
  const visibleMinutes = nodes
    .filter((node) => {
      const day = getStartOfDay(node.createdAt).getTime();
      return day >= startDay && day <= endDay;
    })
    .map((node) => node.createdAt.getHours() * 60 + node.createdAt.getMinutes())
    .sort((a, b) => a - b);

  if (visibleMinutes.length < 2) {
    return { startMinute: 0, endMinute: 1440, tickStep: 180 };
  }

  let bestStart = visibleMinutes[0];
  let bestEnd = visibleMinutes[visibleMinutes.length - 1];
  let bestCount = 0;

  visibleMinutes.forEach((minute, index) => {
    let endIndex = index;
    while (
      endIndex + 1 < visibleMinutes.length &&
      visibleMinutes[endIndex + 1] - minute <= 180
    ) {
      endIndex += 1;
    }
    const count = endIndex - index + 1;
    if (count > bestCount || (count === bestCount && count >= 3)) {
      bestCount = count;
      bestStart = minute;
      bestEnd = visibleMinutes[endIndex];
    }
  });

  const fullSpan =
    visibleMinutes[visibleMinutes.length - 1] - visibleMinutes[0];
  const shouldFocus = bestCount >= 3 || fullSpan <= 240;
  if (!shouldFocus) {
    return { startMinute: 0, endMinute: 1440, tickStep: 180 };
  }

  const minSpan = 180;
  let startMinute = bestStart - 45;
  let endMinute = bestEnd + 45;
  if (endMinute - startMinute < minSpan) {
    const center = (startMinute + endMinute) / 2;
    startMinute = center - minSpan / 2;
    endMinute = center + minSpan / 2;
  }

  startMinute = Math.max(0, Math.floor(startMinute / 15) * 15);
  endMinute = Math.min(1440, Math.ceil(endMinute / 15) * 15);
  const span = endMinute - startMinute;
  const tickStep = span <= 180 ? 15 : span <= 360 ? 30 : span <= 720 ? 60 : 180;

  return { startMinute, endMinute, tickStep };
}

function getDayWidth(plotWidth: number) {
  return plotWidth / Math.max(1, VISIBLE_DAYS);
}

function applyTimeZoom(domain: TimeDomain, zoom: number): TimeDomain {
  if (zoom === 1) return domain;
  const center = (domain.startMinute + domain.endMinute) / 2;
  const baseSpan = domain.endMinute - domain.startMinute;
  const nextSpan = Math.max(60, Math.min(1440, baseSpan / zoom));
  let startMinute = Math.max(0, center - nextSpan / 2);
  let endMinute = Math.min(1440, center + nextSpan / 2);

  if (startMinute === 0) {
    endMinute = Math.min(1440, nextSpan);
  }
  if (endMinute === 1440) {
    startMinute = Math.max(0, 1440 - nextSpan);
  }

  const span = endMinute - startMinute;
  const tickStep = span <= 120 ? 15 : span <= 360 ? 30 : span <= 720 ? 60 : 180;

  return {
    startMinute: Math.floor(startMinute / 15) * 15,
    endMinute: Math.ceil(endMinute / 15) * 15,
    tickStep,
  };
}

function clampToPlot(node: PositionedNode, plot: PlotBox) {
  const padding = node.radius + 4;
  node.x = Math.max(
    plot.left + padding,
    Math.min(plot.left + plot.plotWidth - padding, node.x),
  );
  node.y = Math.max(
    plot.top + padding,
    Math.min(plot.top + plot.plotHeight - padding, node.y),
  );
}

function avoidNodeOverlap(positioned: PositionedNode[], plot: PlotBox) {
  const adjusted = positioned.map((node) => ({ ...node }));
  const visible = adjusted.filter((node) => node.visible);

  for (let iteration = 0; iteration < 8; iteration += 1) {
    for (let i = 0; i < visible.length; i += 1) {
      for (let j = i + 1; j < visible.length; j += 1) {
        const a = visible[i];
        const b = visible[j];
        const minDistance = a.radius + b.radius + 11;
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let distance = Math.hypot(dx, dy);

        if (distance >= minDistance) continue;

        if (distance < 0.1) {
          const angle = ((i * 37 + j * 17) % 360) * (Math.PI / 180);
          dx = Math.cos(angle);
          dy = Math.sin(angle);
          distance = 1;
        }

        const push = (minDistance - distance) / 2;
        const nx = dx / distance;
        const ny = dy / distance;
        a.x -= nx * push;
        a.y -= ny * push;
        b.x += nx * push;
        b.y += ny * push;
        clampToPlot(a, plot);
        clampToPlot(b, plot);
      }
    }
  }

  return adjusted;
}

function clipToPlot(
  ctx: CanvasRenderingContext2D,
  plot: PlotBox,
  callback: () => void,
) {
  ctx.save();
  ctx.beginPath();
  ctx.rect(plot.left, plot.top, plot.plotWidth, plot.plotHeight);
  ctx.clip();
  callback();
  ctx.restore();
}

function drawDayBands(
  ctx: CanvasRenderingContext2D,
  plot: PlotBox,
  startDate: Date,
  dayWidth: number,
  theme: CanvasTheme,
) {
  clipToPlot(ctx, plot, () => {
    for (let index = 0; index < VISIBLE_DAYS; index += 1) {
      const date = addDays(startDate, index);
      const dayKey = Math.floor(getStartOfDay(date).getTime() / ONE_DAY_MS);
      const xStart = plot.left + index * dayWidth;
      ctx.fillStyle = dayKey % 2 === 0 ? theme.dayEven : theme.dayOdd;
      ctx.fillRect(xStart, plot.top, dayWidth, plot.plotHeight);

      ctx.strokeStyle = theme.grid;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(xStart, plot.top);
      ctx.lineTo(xStart, plot.top + plot.plotHeight);
      ctx.stroke();
    }

    ctx.strokeStyle = theme.grid;
    ctx.beginPath();
    ctx.moveTo(plot.left + VISIBLE_DAYS * dayWidth, plot.top);
    ctx.lineTo(plot.left + VISIBLE_DAYS * dayWidth, plot.top + plot.plotHeight);
    ctx.stroke();
  });
}

function calcPositionedNodes(
  nodes: MemoSpacetimeNode[],
  width: number,
  height: number,
  zoom: number,
  dateOffsetDays: number,
) {
  const { left, top, right, bottom } = PLOT_MARGINS;
  const plotWidth = Math.max(1, width - left - right);
  const plotHeight = Math.max(1, height - top - bottom);
  const centerDate = getVisibleCenterDate(dateOffsetDays);
  const startDate = getVisibleStartDate(centerDate);
  const startTime = startDate.getTime();
  const dayWidth = getDayWidth(plotWidth);
  const timeDomain = applyTimeZoom(
    getAdaptiveTimeDomain(nodes, centerDate),
    zoom,
  );
  const timeSpan = Math.max(1, timeDomain.endMinute - timeDomain.startMinute);

  const positioned = nodes.map((node) => {
    const nodeDay = getStartOfDay(node.createdAt);
    const dayDiff = (nodeDay.getTime() - startTime) / ONE_DAY_MS;
    const minutes =
      node.createdAt.getHours() * 60 + node.createdAt.getMinutes();
    const x = left + (dayDiff + 0.5) * dayWidth;
    const y =
      top + ((minutes - timeDomain.startMinute) / timeSpan) * plotHeight;
    const radius = Math.max(9, Math.min(30, 7 + Math.sqrt(node.turns) * 4));
    const visible =
      x > left - radius &&
      x < width - right + radius &&
      y > top - radius &&
      y < height - bottom + radius;

    return { ...node, x, y, radius, visible };
  });

  const plot = { left, top, right, bottom, plotWidth, plotHeight };

  return {
    positioned: avoidNodeOverlap(positioned, plot),
    plot,
    timeDomain,
    dayWidth,
  };
}

type MemoSpacetimeNetworkProps = {
  memories: IMemory[];
  loading?: boolean;
  onCreate?: () => void;
  toolbar?: ReactNode;
};

export function MemoSpacetimeNetwork({
  memories,
  loading,
  onCreate,
  toolbar,
}: MemoSpacetimeNetworkProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const positionedRef = useRef<PositionedNode[]>([]);
  const relationsRef = useRef<PositionedRelation[]>([]);
  const dragRef = useRef({ dragging: false, lastX: 0 });
  const [canvasSize, setCanvasSize] = useState({ width: 960, height: 620 });
  const [zoom, setZoom] = useState(1);
  const [dateOffsetDays, setDateOffsetDays] = useState(0);
  const [themeVersion, setThemeVersion] = useState(0);
  const [hoveredId, setHoveredId] = useState<string>();
  const [hoveredRelation, setHoveredRelation] = useState<PositionedRelation>();
  const [tooltip, setTooltip] = useState<{ x: number; y: number }>();
  const [relationTooltip, setRelationTooltip] = useState<{
    x: number;
    y: number;
  }>();
  const [selectedId, setSelectedId] = useState<string>();
  const [focusDate, setFocusDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [profileOpening, setProfileOpening] = useState(false);
  const [dateFocusReport, setDateFocusReport] = useState<DateFocusReport>();
  const [keywordWeaveReport, setKeywordWeaveReport] =
    useState<KeywordWeaveReport>();
  const [activeKeyword, setActiveKeyword] = useState<string>();
  const [dashOffset, setDashOffset] = useState(0);

  const rawNodes = useMemo(
    () => memories.map((memory) => buildNode(memory, t)),
    [memories, t],
  );
  const nodes = useMemo(() => groupCanonicalNodes(rawNodes), [rawNodes]);
  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedId),
    [nodes, selectedId],
  );

  const hoveredNode = useMemo(
    () => nodes.find((node) => node.id === hoveredId),
    [hoveredId, nodes],
  );

  const firstNodeDate = useMemo(() => {
    const first = nodes.reduce<Date | undefined>((earliest, node) => {
      if (!earliest) return node.createdAt;
      return node.createdAt.getTime() < earliest.getTime()
        ? node.createdAt
        : earliest;
    }, undefined);
    return first ? getStartOfDay(first) : getStartOfDay(new Date());
  }, [nodes]);

  const selectedRelatedNodes = useMemo(() => {
    if (!selectedNode) return [];
    return nodes
      .filter((node) => node.id !== selectedNode.id)
      .map((node) => ({
        node,
        shared: getSharedKeywords(selectedNode, node),
      }))
      .filter((item) => item.shared.length > 0)
      .sort((a, b) => b.shared.length - a.shared.length);
  }, [nodes, selectedNode]);

  const setViewportToDate = useCallback((date: Date) => {
    const today = getStartOfDay(new Date()).getTime();
    setDateOffsetDays((getStartOfDay(date).getTime() - today) / ONE_DAY_MS);
  }, []);

  const focusNode = useCallback(
    (node: MemoSpacetimeNode) => {
      setSelectedId(node.id);
      setFocusDate(formatInputDate(node.createdAt));
      setViewportToDate(node.createdAt);
    },
    [setViewportToDate],
  );

  const buildDateReport = useCallback(
    (inputValue: string) => {
      const date = new Date(inputValue);
      if (Number.isNaN(date.getTime())) return;
      const target = getStartOfDay(date);
      const nodesOnDay = nodes
        .filter((node) => isSameDay(node.createdAt, target))
        .sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime());

      setViewportToDate(target);
      setActiveKeyword(undefined);
      setKeywordWeaveReport(undefined);

      if (!nodesOnDay.length) {
        setSelectedId(undefined);
        setDateFocusReport({
          dateLabel: formatDay(target),
          nodeCount: 0,
          turnCount: 0,
          categories: [],
          timeRange: t('memories.spacetime.noTimeRange', {
            defaultValue: 'No records',
          }),
          hasNodes: false,
        });
        return;
      }

      const categories = Array.from(
        new Set(nodesOnDay.map((node) => node.memoryTypeLabel)),
      );
      const turnCount = nodesOnDay.reduce((sum, node) => sum + node.turns, 0);
      const first = nodesOnDay[0].createdAt;
      const last = nodesOnDay[nodesOnDay.length - 1].createdAt;

      setSelectedId(nodesOnDay[0].id);
      setDateFocusReport({
        dateLabel: formatDay(target),
        nodeCount: nodesOnDay.length,
        turnCount,
        categories,
        timeRange: `${formatTime(first)} - ${formatTime(last)}`,
        hasNodes: true,
      });
    },
    [nodes, setViewportToDate, t],
  );

  const analyzeKeywordConnections = useCallback(() => {
    const counts = nodes.reduce<Record<string, number>>((acc, node) => {
      getLinkKeywords(node).forEach((keyword) => {
        acc[keyword] = (acc[keyword] || 0) + 1;
      });
      return acc;
    }, {});
    const repeated = Object.entries(counts)
      .filter(([, count]) => count > 1)
      .sort((a, b) => b[1] - a[1]);

    if (!repeated.length) {
      setActiveKeyword(undefined);
      setKeywordWeaveReport(undefined);
      return;
    }

    const topKeyword = repeated[0][0];
    const connectedNodes = nodes.filter((node) =>
      node.keywords.includes(topKeyword),
    );
    const primaryNode = connectedNodes.reduce(
      (best, node) => {
        const score = nodes.filter(
          (other) =>
            other.id !== node.id && sharedKeywordCount(node, other) > 0,
        ).length;
        return score > best.score ? { node, score } : best;
      },
      { node: connectedNodes[0], score: 0 },
    ).node;
    const timestamps = connectedNodes.map((node) =>
      getStartOfDay(node.createdAt).getTime(),
    );
    const daySpan =
      Math.round(
        (Math.max(...timestamps) - Math.min(...timestamps)) / ONE_DAY_MS,
      ) + 1;

    setActiveKeyword(topKeyword);
    setKeywordWeaveReport({
      topKeyword,
      topKeywords: repeated.slice(0, 3),
      connectedCount: connectedNodes.length,
      daySpan,
      primaryTopic: primaryNode.topic,
    });
    focusNode(primaryNode);
  }, [focusNode, nodes]);

  useEffect(() => {
    setSelectedId((current) =>
      current && nodes.some((node) => node.id === current)
        ? current
        : nodes[0]?.id,
    );
  }, [nodes]);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;

    const updateSize = () => {
      const rect = wrapper.getBoundingClientRect();
      setCanvasSize({
        width: Math.max(680, rect.width),
        height: Math.max(520, rect.height),
      });
    };
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const observer = new MutationObserver(() =>
      setThemeVersion((version) => version + 1),
    );
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!activeKeyword && !selectedId && !hoveredId && !hoveredRelation) return;
    let frame = 0;
    let disposed = false;
    const tick = () => {
      if (disposed) return;
      setDashOffset((current) => (current - 0.6) % 24);
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => {
      disposed = true;
      window.cancelAnimationFrame(frame);
    };
  }, [activeKeyword, hoveredId, hoveredRelation, selectedId]);

  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = canvasSize.width * dpr;
    canvas.height = canvasSize.height * dpr;
    canvas.style.width = `${canvasSize.width}px`;
    canvas.style.height = `${canvasSize.height}px`;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const theme = getCanvasTheme();
    ctx.clearRect(0, 0, canvasSize.width, canvasSize.height);
    ctx.fillStyle = theme.background;
    ctx.fillRect(0, 0, canvasSize.width, canvasSize.height);

    const { positioned, plot, timeDomain, dayWidth } = calcPositionedNodes(
      nodes,
      canvasSize.width,
      canvasSize.height,
      zoom,
      dateOffsetDays,
    );
    positionedRef.current = positioned;

    ctx.fillStyle = theme.panel;
    ctx.fillRect(plot.left, plot.top, plot.plotWidth, plot.plotHeight);
    const centerDate = getVisibleCenterDate(dateOffsetDays);
    const startDate = getVisibleStartDate(centerDate);
    drawDayBands(ctx, plot, startDate, dayWidth, theme);

    ctx.fillStyle = theme.muted;
    ctx.font = '600 12px Inter, sans-serif';
    ctx.fillText(
      t('memories.spacetime.dateAxis', { defaultValue: 'Date' }),
      plot.left - 62,
      plot.top - 8,
    );
    ctx.fillText(
      t('memories.spacetime.timeAxis', { defaultValue: 'Time' }),
      plot.left - 36,
      plot.top + 4,
    );

    ctx.strokeStyle = theme.grid;
    ctx.lineWidth = 1;
    for (
      let minute =
        Math.ceil(timeDomain.startMinute / timeDomain.tickStep) *
        timeDomain.tickStep;
      minute <= timeDomain.endMinute;
      minute += timeDomain.tickStep
    ) {
      const y =
        plot.top +
        ((minute - timeDomain.startMinute) /
          (timeDomain.endMinute - timeDomain.startMinute)) *
          plot.plotHeight;
      ctx.beginPath();
      ctx.moveTo(plot.left, y);
      ctx.lineTo(canvasSize.width - plot.right, y);
      ctx.stroke();
      ctx.fillStyle = minute % 60 === 0 ? theme.text : theme.muted;
      ctx.font = '12px Inter, sans-serif';
      ctx.fillText(formatMinuteLabel(minute), 14, y + 4);
    }

    const today = getStartOfDay(new Date()).getTime();
    for (let index = 0; index < VISIBLE_DAYS; index += 1) {
      const x = plot.left + index * dayWidth + dayWidth / 2;
      const date = addDays(startDate, index);
      const isToday = getStartOfDay(date).getTime() === today;
      ctx.fillStyle = isToday ? theme.accent : theme.muted;
      ctx.font = isToday
        ? '600 12px Inter, sans-serif'
        : '12px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(formatDayWithWeekday(date, i18n.language), x, 34);
    }
    ctx.textAlign = 'left';

    const activeNodeId = hoveredId || selectedId;
    const relations = buildVisibleRelations(positioned, dayWidth);
    relationsRef.current = relations;
    relations.forEach((relation) => {
      const isNodeActive =
        activeNodeId &&
        (relation.source.id === activeNodeId ||
          relation.target.id === activeNodeId);
      const isKeywordActive =
        activeKeyword &&
        relation.source.keywords.includes(activeKeyword) &&
        relation.target.keywords.includes(activeKeyword);
      const isRelationActive = relation.id === hoveredRelation?.id;
      const isActive = isNodeActive || isKeywordActive || isRelationActive;
      ctx.strokeStyle = isActive ? theme.accent : theme.edge;
      ctx.globalAlpha = isRelationActive ? 0.72 : isActive ? 0.56 : 1;
      ctx.lineWidth = isRelationActive
        ? 2.2
        : isActive
          ? 1.65
          : Math.min(1.15, 0.9 + relation.sharedKeywords.length * 0.08);
      if (isActive) {
        ctx.setLineDash(isRelationActive ? [5, 6] : [6, 9]);
        ctx.lineDashOffset = dashOffset;
        ctx.shadowColor = theme.accent;
        ctx.shadowBlur = isRelationActive ? 9 : 5;
      } else {
        ctx.setLineDash([]);
        ctx.shadowBlur = 0;
      }
      traceRelationPath(ctx, relation);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.shadowBlur = 0;
      ctx.globalAlpha = 1;
    });

    positioned.forEach((node) => {
      if (!node.visible) return;
      const isSelected = node.id === selectedId;
      const isHovered = node.id === hoveredId;
      const color = getNodeColor(node);

      const isKeywordActive =
        activeKeyword && node.keywords.includes(activeKeyword);

      ctx.shadowColor =
        isSelected || isHovered || isKeywordActive ? color : 'transparent';
      ctx.shadowBlur = isSelected || isHovered || isKeywordActive ? 18 : 0;
      ctx.fillStyle = color;
      ctx.globalAlpha =
        isSelected || isHovered || isKeywordActive ? 0.98 : 0.82;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.shadowBlur = 0;
      ctx.strokeStyle =
        isSelected || isHovered || isKeywordActive
          ? theme.activeStroke
          : theme.nodeStroke;
      ctx.lineWidth = isSelected || isHovered || isKeywordActive ? 3 : 1.4;
      ctx.stroke();

      ctx.fillStyle = theme.text;
      ctx.font = '600 11px Inter, sans-serif';
      ctx.textAlign = 'center';
      const label =
        node.topic.length > 12 ? `${node.topic.slice(0, 12)}...` : node.topic;
      ctx.fillText(label, node.x, node.y + node.radius + 16);
    });
    ctx.textAlign = 'left';
  }, [
    activeKeyword,
    canvasSize.height,
    canvasSize.width,
    dashOffset,
    dateOffsetDays,
    hoveredId,
    hoveredRelation?.id,
    i18n.language,
    nodes,
    selectedId,
    t,
    zoom,
  ]);

  useEffect(() => {
    drawCanvas();
  }, [drawCanvas, themeVersion]);

  const findNode = useCallback((x: number, y: number) => {
    return [...positionedRef.current]
      .reverse()
      .find(
        (node) =>
          node.visible &&
          Math.hypot(node.x - x, node.y - y) <= Math.max(node.radius + 4, 16),
      );
  }, []);

  const getCanvasPoint = useCallback(
    (event: ReactMouseEvent<HTMLCanvasElement>) => {
      const rect = event.currentTarget.getBoundingClientRect();
      return {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      };
    },
    [],
  );

  const handleMouseMove = useCallback(
    (event: ReactMouseEvent<HTMLCanvasElement>) => {
      const point = getCanvasPoint(event);
      if (dragRef.current.dragging) {
        const deltaX = point.x - dragRef.current.lastX;
        dragRef.current.lastX = point.x;
        const plotWidth = Math.max(
          1,
          canvasSize.width - PLOT_MARGINS.left - PLOT_MARGINS.right,
        );
        setDateOffsetDays(
          (current) => current - deltaX / getDayWidth(plotWidth),
        );
        return;
      }

      const node = findNode(point.x, point.y);
      if (node) {
        setHoveredId(node.id);
        setTooltip({ x: point.x, y: point.y });
        setHoveredRelation(undefined);
        setRelationTooltip(undefined);
        event.currentTarget.style.cursor = 'pointer';
        return;
      }

      const relation = findNearestRelation(
        point.x,
        point.y,
        relationsRef.current,
      );
      setHoveredId(undefined);
      setTooltip(undefined);
      setHoveredRelation(relation);
      setRelationTooltip(relation ? { x: point.x, y: point.y } : undefined);
      event.currentTarget.style.cursor = relation ? 'help' : 'grab';
    },
    [canvasSize.width, findNode, getCanvasPoint],
  );

  const handleMouseDown = useCallback(
    (event: ReactMouseEvent<HTMLCanvasElement>) => {
      const point = getCanvasPoint(event);
      const node = findNode(point.x, point.y);
      if (node) {
        setSelectedId(node.id);
        return;
      }
      const relation = findNearestRelation(
        point.x,
        point.y,
        relationsRef.current,
      );
      if (relation) {
        setSelectedId(relation.source.id);
        setHoveredRelation(relation);
        setRelationTooltip({ x: point.x, y: point.y });
        return;
      }
      dragRef.current = { dragging: true, lastX: point.x };
      event.currentTarget.style.cursor = 'grabbing';
    },
    [findNode, getCanvasPoint],
  );

  const handleMouseUp = useCallback(() => {
    dragRef.current.dragging = false;
  }, []);

  const handleMouseLeave = useCallback(() => {
    dragRef.current.dragging = false;
    setHoveredId(undefined);
    setTooltip(undefined);
    setHoveredRelation(undefined);
    setRelationTooltip(undefined);
  }, []);

  const handleWheelDelta = useCallback(
    (deltaY: number, ctrlKey?: boolean, metaKey?: boolean) => {
      if (ctrlKey || metaKey) {
        setZoom((current) =>
          Math.min(2.2, Math.max(0.55, current - deltaY * 0.0015)),
        );
        return;
      }
      setDateOffsetDays((current) => current + deltaY / 360);
    },
    [],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      handleWheelDelta(event.deltaY, event.ctrlKey, event.metaKey);
    };

    canvas.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      canvas.removeEventListener('wheel', handleWheel);
    };
  }, [handleWheelDelta]);

  const openMemory = useCallback(
    (id: string) => {
      navigate(`${Routes.Memory}${Routes.MemoryMessage}/${id}`);
    },
    [navigate],
  );
  const openProfile = useCallback(() => {
    setProfileOpening(true);
    window.sessionStorage.setItem(DEV_FEATURE_SESSION_KEY, '1');
    window.setTimeout(() => {
      navigate(Routes.MemoriesProfile);
    }, 80);
  }, [navigate]);

  const resetViewport = useCallback(() => {
    setZoom(1);
    setDateOffsetDays(0);
    setFocusDate(formatInputDate(new Date()));
    setDateFocusReport(undefined);
    setKeywordWeaveReport(undefined);
    setActiveKeyword(undefined);
    setSelectedId(nodes[0]?.id);
  }, [nodes]);

  const focusOnDate = useCallback(() => {
    buildDateReport(focusDate);
  }, [buildDateReport, focusDate]);

  const shiftDays = useCallback(
    (days: number, resetToFirst = false) => {
      if (resetToFirst) {
        setViewportToDate(firstNodeDate);
        setFocusDate(formatInputDate(firstNodeDate));
      } else {
        setDateOffsetDays((current) => current + days);
      }
      setActiveKeyword(undefined);
      setKeywordWeaveReport(undefined);
    },
    [firstNodeDate, setViewportToDate],
  );

  const topKeywords = useMemo(() => {
    const counts = nodes.reduce<Record<string, number>>((acc, node) => {
      getLinkKeywords(node).forEach((keyword) => {
        acc[keyword] = (acc[keyword] || 0) + 1;
      });
      return acc;
    }, {});

    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
  }, [nodes]);

  const legendItems = useMemo(() => {
    const map = new Map<MemoCategory, string>();
    nodes.forEach((node) => {
      if (!map.has(node.category)) {
        map.set(node.category, node.memoryTypeLabel);
      }
    });
    return Array.from(map.entries()).slice(0, 5);
  }, [nodes]);

  const keywordLegendItems = useMemo(
    () => topKeywords.slice(0, 5),
    [topKeywords],
  );

  return (
    <section className="mx-3 mb-3 mt-3 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[#e6dcd8] bg-[#fbf7f5] text-[#263241] shadow-sm dark:border-slate-800 dark:bg-[#070b14] dark:text-slate-100 dark:shadow-2xl">
      <header className="flex shrink-0 items-center justify-between gap-4 border-b border-[#e6dcd8] bg-white/80 px-5 py-2.5 backdrop-blur dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-gradient-to-tr from-[#7f435b] via-[#496985] to-[#355d84] shadow-lg shadow-[#7f435b]/15 dark:from-indigo-500 dark:via-blue-600 dark:to-purple-600 dark:shadow-indigo-500/20">
            <Network className="size-6 text-white" />
          </div>
          <div>
            <h2 className="text-xl font-extrabold tracking-wide text-[#263241] dark:text-slate-100">
              {t('memories.spacetime.title', {
                defaultValue: 'Memory spacetime',
              })}
            </h2>
            <p className="text-xs text-[#65717e] dark:text-slate-400">
              {t('memories.spacetime.subtitle', {
                defaultValue:
                  'Topics are placed by creation date and time. Radius reflects conversation turns.',
              })}
            </p>
          </div>
        </div>
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          {toolbar && (
            <div className="rounded-full border border-[#e6dcd8] bg-white/90 px-2 py-1 shadow-sm dark:border-slate-800 dark:bg-slate-950/70">
              {toolbar}
            </div>
          )}
          <Button
            size="sm"
            variant="outline"
            className="border-[#d8c9c4] bg-white text-[#4f5865] hover:bg-[#f2e9e5] dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700"
            onClick={resetViewport}
          >
            <RotateCcw className="size-4" />
            {t('memories.spacetime.reset', { defaultValue: 'Reset viewport' })}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="border-[#d8b9c4] bg-[#f8f1ef] text-[#6d334a] hover:bg-[#ead8d2] dark:border-indigo-800/60 dark:bg-indigo-950/70 dark:text-indigo-200 dark:hover:bg-indigo-900"
            onClick={openProfile}
            disabled={profileOpening}
          >
            {profileOpening ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <BrainCircuit className="size-4" />
            )}
            {t('memories.profile.openProfile', {
              defaultValue: 'Open thinking profile',
            })}
          </Button>
          <div className="rounded-md border border-[#e6dcd8] bg-white px-3 py-1.5 text-xs text-[#7b818b] dark:border-slate-800 dark:bg-slate-950 dark:text-slate-500">
            {t('memories.spacetime.loaded', {
              defaultValue: 'Memory center loaded',
            })}
            :{' '}
            <span className="font-bold text-[#8d4660] dark:text-indigo-400">
              {nodes.length}
            </span>{' '}
            {t('memories.spacetime.nodes', { defaultValue: 'nodes' })}
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="flex w-96 shrink-0 flex-col overflow-y-auto border-r border-[#e6dcd8] bg-[#f8f1ef] shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:shadow-2xl">
          <div className="border-b border-[#e6dcd8] p-5 dark:border-slate-800">
            <h3 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#68717d] dark:text-slate-400">
              <span className="size-1.5 rounded-full bg-[#8d4660] dark:bg-indigo-500" />
              {t('memories.spacetime.viewportControls', {
                defaultValue: 'Viewport dimensions and panning',
              })}
            </h3>
            <div className="mb-4">
              <label className="mb-2 block text-[11px] text-[#68717d] dark:text-slate-400">
                {t('memories.spacetime.horizontalPan', {
                  defaultValue:
                    'Horizontal date panning. You can also drag the canvas.',
                })}
              </label>
              <div className="grid grid-cols-5 gap-1">
                <button
                  type="button"
                  onClick={() => shiftDays(-6)}
                  className="flex items-center justify-center gap-1 rounded border border-[#d8c9c4] dark:border-slate-700/80 bg-[#eee4e0] dark:bg-slate-800 py-1.5 text-xs font-medium text-[#45515f] dark:text-slate-300 transition hover:bg-[#e4d7d2] dark:hover:bg-slate-700"
                >
                  <SkipBack className="size-3.5" />
                  -6d
                </button>
                <button
                  type="button"
                  onClick={() => shiftDays(-1)}
                  className="flex items-center justify-center gap-1 rounded border border-[#d8c9c4] dark:border-slate-700/80 bg-[#eee4e0] dark:bg-slate-800 py-1.5 text-xs font-medium text-[#45515f] dark:text-slate-300 transition hover:bg-[#e4d7d2] dark:hover:bg-slate-700"
                >
                  <ChevronLeft className="size-3.5" />
                  -1d
                </button>
                <button
                  type="button"
                  onClick={() => shiftDays(0, true)}
                  className="rounded border border-[#d8b9c4] bg-[#f4e9e6] py-1.5 text-xs font-bold text-[#7f435b] transition hover:bg-[#ead8d2] dark:border-indigo-800/80 dark:bg-indigo-950/60 dark:text-indigo-300 dark:hover:bg-indigo-900/70"
                >
                  {t('memories.spacetime.firstDay', {
                    defaultValue: 'First',
                  })}
                </button>
                <button
                  type="button"
                  onClick={() => shiftDays(1)}
                  className="flex items-center justify-center gap-1 rounded border border-[#d8c9c4] dark:border-slate-700/80 bg-[#eee4e0] dark:bg-slate-800 py-1.5 text-xs font-medium text-[#45515f] dark:text-slate-300 transition hover:bg-[#e4d7d2] dark:hover:bg-slate-700"
                >
                  +1d
                  <ChevronRight className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => shiftDays(6)}
                  className="flex items-center justify-center gap-1 rounded border border-[#d8c9c4] dark:border-slate-700/80 bg-[#eee4e0] dark:bg-slate-800 py-1.5 text-xs font-medium text-[#45515f] dark:text-slate-300 transition hover:bg-[#e4d7d2] dark:hover:bg-slate-700"
                >
                  +6d
                  <SkipForward className="size-3.5" />
                </button>
              </div>
            </div>
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label className="text-xs font-medium text-[#68717d] dark:text-slate-400">
                  {t('memories.spacetime.globalZoom', {
                    defaultValue: 'Proportional canvas zoom',
                  })}
                </label>
                <span className="font-mono text-xs font-bold text-[#8d4660] dark:text-indigo-400">
                  {Math.round(zoom * 100)}%
                </span>
              </div>
              <input
                aria-label={t('memories.spacetime.zoom', {
                  defaultValue: 'Zoom',
                })}
                type="range"
                min="0.5"
                max="2.5"
                step="0.05"
                value={zoom}
                onChange={(event) => setZoom(Number(event.target.value))}
                className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-[#eee4e0] dark:bg-slate-800 accent-[#8d4660] dark:accent-indigo-500"
              />
              <div className="mt-1 flex justify-between text-[10px] text-[#83818a] dark:text-slate-500">
                <span>50%</span>
                <span className="text-[#8d4660] dark:text-indigo-500">
                  100%
                </span>
                <span>250%</span>
              </div>
            </div>
          </div>

          <div className="border-b border-[#e6dcd8] dark:border-slate-800 bg-[#f8f1ef] dark:bg-slate-900/40 p-5">
            <h3 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#68717d] dark:text-slate-400">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              {t('memories.spacetime.spacetimeClues', {
                defaultValue: 'Spacetime clues',
              })}
            </h3>
            <div className="space-y-4">
              <div className="rounded-xl border border-[#e6dcd8] bg-white p-3 transition hover:border-[#d8c9c4] dark:border-slate-800 dark:bg-slate-950/80 dark:hover:border-slate-700">
                <label className="mb-1 block text-[10px] text-[#83818a] dark:text-slate-500">
                  {t('memories.spacetime.focusDateHint', {
                    defaultValue: 'Choose a focus date. Updates immediately.',
                  })}
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="date"
                    value={focusDate}
                    onChange={(event) => {
                      setFocusDate(event.target.value);
                      buildDateReport(event.target.value);
                    }}
                    className="min-w-0 flex-1 rounded-lg border border-[#e6dcd8] bg-[#f8f1ef] px-3 py-2 text-center font-mono text-xs font-bold text-[#263241] outline-none transition hover:bg-[#eee4e0] focus:border-[#c9899d] dark:border-slate-800 dark:bg-slate-900 dark:text-white dark:hover:bg-slate-800 dark:focus:border-indigo-500 dark:[&::-webkit-calendar-picker-indicator]:brightness-200 dark:[&::-webkit-calendar-picker-indicator]:invert dark:[&::-webkit-calendar-picker-indicator]:opacity-100"
                  />
                  <button
                    type="button"
                    onClick={focusOnDate}
                    className="rounded-lg border border-[#d8b9c4] bg-[#f4e9e6] p-2 text-[#7f435b] transition hover:bg-[#ead8d2] dark:border-indigo-800/60 dark:bg-indigo-950/50 dark:text-indigo-300 dark:hover:bg-indigo-900/70"
                  >
                    <LocateFixed className="size-4" />
                  </button>
                </div>
                {dateFocusReport && (
                  <div
                    className={
                      dateFocusReport.hasNodes
                        ? 'mt-3.5 space-y-2.5 rounded-xl border border-[#c9899d] dark:border-indigo-500/25 bg-[#f4e9e6] dark:bg-indigo-950/45 p-3.5 text-xs'
                        : 'mt-3.5 space-y-1.5 rounded-xl border border-[#e6dcd8] dark:border-slate-800/80 bg-white dark:bg-slate-950 p-3.5 text-xs text-[#68717d] dark:text-slate-400'
                    }
                  >
                    <div className="flex items-center gap-1.5 border-b border-indigo-900/40 pb-1.5 font-bold text-[#7f435b] dark:text-indigo-300">
                      <span className="size-2 rounded-full bg-indigo-400" />
                      {dateFocusReport.hasNodes
                        ? t('memories.spacetime.memoryExtraction', {
                            date: dateFocusReport.dateLabel,
                            defaultValue: 'Memo extraction [{{date}}]',
                          })
                        : t('memories.spacetime.noDateNodes', {
                            defaultValue: 'No memo data at this coordinate',
                          })}
                    </div>
                    {dateFocusReport.hasNodes ? (
                      <>
                        <div className="grid grid-cols-2 gap-2 text-[#45515f] dark:text-slate-300">
                          <div className="rounded border border-[#d8b9c4] dark:border-indigo-800/20 bg-[#f4e9e6] dark:bg-indigo-950/20 p-2">
                            <span className="block text-[9px] text-[#83818a] dark:text-slate-500">
                              {t('memories.spacetime.memoryFrequency', {
                                defaultValue: 'Memo frequency',
                              })}
                            </span>
                            <span className="font-mono text-sm font-bold text-[#263241] dark:text-white">
                              {dateFocusReport.nodeCount}
                            </span>
                          </div>
                          <div className="rounded border border-[#d8b9c4] dark:border-indigo-800/20 bg-[#f4e9e6] dark:bg-indigo-950/20 p-2">
                            <span className="block text-[9px] text-[#83818a] dark:text-slate-500">
                              {t('memories.spacetime.totalTurns', {
                                defaultValue: 'Total turns',
                              })}
                            </span>
                            <span className="font-mono text-sm font-bold text-[#263241] dark:text-white">
                              {dateFocusReport.turnCount}
                            </span>
                          </div>
                        </div>
                        <div className="space-y-1 text-[11px] leading-normal text-[#68717d] dark:text-slate-400">
                          <div>
                            {t('memories.spacetime.containsCategories', {
                              defaultValue: 'Categories',
                            })}
                            :{' '}
                            <span className="font-bold text-[#6d334a] dark:text-indigo-200">
                              {dateFocusReport.categories.join(', ')}
                            </span>
                          </div>
                          <div>
                            {t('memories.spacetime.timeSpan', {
                              defaultValue: 'Time span',
                            })}
                            :{' '}
                            <span className="font-bold text-[#6d334a] dark:text-indigo-200">
                              {dateFocusReport.timeRange}
                            </span>
                          </div>
                        </div>
                      </>
                    ) : (
                      <p className="text-[11px] leading-relaxed">
                        {t('memories.spacetime.emptyDateHint', {
                          defaultValue:
                            'The viewport has moved to this empty coordinate.',
                        })}
                      </p>
                    )}
                  </div>
                )}
              </div>

              <div className="rounded-xl border border-[#e6dcd8] bg-white p-3 transition hover:border-[#d8c9c4] dark:border-slate-800 dark:bg-slate-950/80 dark:hover:border-slate-700">
                <span className="mb-1 block text-xs font-bold text-[#8d4660] dark:text-indigo-400">
                  {t('memories.spacetime.keywordClues', {
                    defaultValue: 'Keyword horizontal clues',
                  })}
                </span>
                <p className="mb-2.5 text-[10px] leading-normal text-[#68717d] dark:text-slate-400">
                  {t('memories.spacetime.keywordCluesDescription', {
                    defaultValue:
                      'Cluster overlapping keywords across time and locate the strongest similar circuit.',
                  })}
                </p>
                <button
                  type="button"
                  onClick={analyzeKeywordConnections}
                  className="flex w-full items-center justify-center gap-1 rounded border border-[#c9899d] bg-[#8d4660]/10 py-1.5 text-xs font-bold text-[#7f435b] transition hover:bg-[#8d4660]/15 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/20"
                >
                  <GitBranch className="size-3.5" />
                  {t('memories.spacetime.analyzeGlobalWeave', {
                    defaultValue: 'Analyze global strongest weave',
                  })}
                </button>
                {keywordWeaveReport ? (
                  <div className="mt-3.5 space-y-2.5 rounded-xl border border-[#c9899d] dark:border-indigo-500/25 bg-[#f4e9e6] dark:bg-indigo-950/45 p-3.5 text-xs">
                    <div className="flex items-center gap-1.5 border-b border-indigo-900/40 pb-1.5 font-bold text-[#7f435b] dark:text-indigo-300">
                      <Share2 className="size-3.5" />
                      {t('memories.spacetime.horizontalReport', {
                        defaultValue: 'Horizontal clue report',
                      })}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="mr-1 block text-[10px] text-[#68717d] dark:text-slate-400">
                        {t('memories.spacetime.strongTies', {
                          defaultValue: 'Strong ties',
                        })}
                        :
                      </span>
                      {keywordWeaveReport.topKeywords.map(
                        ([keyword, count]) => (
                          <span
                            key={keyword}
                            className="rounded border border-[#c9899d] dark:border-indigo-500/30 bg-[#f4e9e6] dark:bg-indigo-950/60 px-2 py-0.5 font-mono text-[10px] font-bold text-[#7f435b] dark:text-indigo-300"
                          >
                            {keyword} ({count})
                          </span>
                        ),
                      )}
                    </div>
                    <div className="space-y-1.5 text-[11px] text-[#45515f] dark:text-slate-300">
                      <p>
                        {t('memories.spacetime.subnetwork', {
                          defaultValue: 'Related subnetwork',
                        })}
                        :{' '}
                        <span className="font-mono text-sm font-bold text-[#263241] dark:text-white">
                          {keywordWeaveReport.connectedCount}
                        </span>
                      </p>
                      <p>
                        {t('memories.spacetime.horizontalSpan', {
                          defaultValue: 'Horizontal time span',
                        })}
                        :{' '}
                        <span className="font-mono text-sm font-bold text-[#263241] dark:text-white">
                          {keywordWeaveReport.daySpan}
                        </span>
                      </p>
                    </div>
                    <p className="border-t border-indigo-900/40 pt-1 text-[10px] italic leading-normal text-[#68717d] dark:text-slate-400">
                      {t('memories.spacetime.primaryNodeHint', {
                        topic: keywordWeaveReport.primaryTopic,
                        defaultValue:
                          'Located the core hub node: {{topic}}. The related weave is highlighted.',
                      })}
                    </p>
                  </div>
                ) : topKeywords.length ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {topKeywords.slice(0, 8).map(([keyword, count]) => (
                      <span
                        key={keyword}
                        className="inline-flex items-center gap-1 rounded-full bg-[#f4e9e6] dark:bg-indigo-950/50 px-2 py-0.5 text-[10px] text-[#7f435b] dark:text-indigo-300"
                      >
                        <span
                          className="size-1.5 rounded-full"
                          style={{ backgroundColor: getKeywordColor(keyword) }}
                        />
                        {keyword} · {count}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-xs italic text-[#83818a] dark:text-slate-500">
                    {t('memories.spacetime.noKeywords', {
                      defaultValue: 'No keyword links yet.',
                    })}
                  </p>
                )}
              </div>
            </div>
          </div>

          <div className="flex-grow p-5">
            <h3 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-[#68717d] dark:text-slate-400">
              <span className="size-1.5 rounded-full bg-purple-500" />
              {t('memories.spacetime.selectedPointInfo', {
                defaultValue: 'Selected memory point',
              })}
            </h3>
            {selectedNode ? (
              <div className="rounded-xl border border-[#e6dcd8] dark:border-slate-800 bg-white dark:bg-slate-950 p-4 shadow-xl shadow-indigo-950/20">
                <div className="mb-3 flex items-start justify-between">
                  <span
                    className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white"
                    style={{
                      backgroundColor: getNodeColor(selectedNode),
                    }}
                  >
                    {getNodePrimaryKeyword(selectedNode)}
                  </span>
                  <span className="font-mono text-xs text-[#83818a] dark:text-slate-500">
                    ID: {selectedNode.primaryMemoryId.slice(0, 8)}
                  </span>
                </div>
                <h4 className="mb-2.5 line-clamp-3 text-sm font-bold leading-snug text-[#2f3a46] dark:text-slate-200">
                  {selectedNode.topic}
                </h4>
                <div className="mb-3 grid grid-cols-2 gap-2 rounded-lg border border-[#e6dcd8] dark:border-slate-800/80 bg-[#f8f1ef] dark:bg-slate-900/60 p-2.5 text-xs">
                  <div>
                    <span className="block text-[10px] text-[#83818a] dark:text-slate-500">
                      {t('memories.spacetime.createdDate', {
                        defaultValue: 'Date',
                      })}
                    </span>
                    <span className="font-mono font-bold text-[#45515f] dark:text-slate-300">
                      {formatInputDate(selectedNode.createdAt)}
                    </span>
                  </div>
                  <div>
                    <span className="block text-[10px] text-[#83818a] dark:text-slate-500">
                      {t('memories.spacetime.exactTime', {
                        defaultValue: 'Time',
                      })}
                    </span>
                    <span className="font-mono font-bold text-[#45515f] dark:text-slate-300">
                      {formatTime(selectedNode.createdAt)}
                    </span>
                  </div>
                </div>
                <div className="mb-3.5">
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="flex items-center gap-1 text-[#68717d] dark:text-slate-400">
                      <MessageSquareText className="size-3.5 text-[#8d4660] dark:text-indigo-400" />
                      {t('memories.spacetime.turnsScale', {
                        defaultValue: 'Conversation turns',
                      })}
                    </span>
                    <span className="font-mono font-bold text-[#8d4660] dark:text-indigo-400">
                      {selectedNode.turns}
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-[#eee4e0] dark:bg-slate-800">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500"
                      style={{
                        width: `${Math.min(100, (selectedNode.turns / 20) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
                <div className="mb-4">
                  <span className="mb-1.5 block text-[10px] text-[#83818a] dark:text-slate-500">
                    {t('memories.spacetime.coreKeywords', {
                      defaultValue: 'Core keywords',
                    })}
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedNode.keywords.slice(0, 10).map((keyword) => (
                      <span
                        key={keyword}
                        className="rounded border border-[#c9899d] bg-[#8d4660]/10 px-2 py-0.5 text-[11px] text-[#45515f] dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-slate-300"
                      >
                        # {keyword}
                      </span>
                    ))}
                  </div>
                </div>
                {selectedNode.preview && (
                  <p className="mb-4 line-clamp-5 whitespace-pre-line rounded-lg border border-[#e6dcd8] dark:border-slate-800 bg-[#f8f1ef] dark:bg-slate-900/60 p-2.5 text-xs leading-5 text-[#68717d] dark:text-slate-400">
                    {selectedNode.preview}
                  </p>
                )}
                <div className="border-t border-[#e6dcd8] dark:border-slate-800 pt-3">
                  <span className="mb-2 flex items-center gap-1 text-[10px] font-bold text-[#68717d] dark:text-slate-400">
                    <span className="size-1.5 rounded-full bg-indigo-400" />
                    {t('memories.spacetime.sharedMemos', {
                      defaultValue: 'Shared related memos',
                    })}
                  </span>
                  <div className="max-h-40 space-y-1.5 overflow-y-auto">
                    {selectedRelatedNodes.length ? (
                      selectedRelatedNodes.map(({ node, shared }) => (
                        <button
                          type="button"
                          key={node.id}
                          onClick={() => focusNode(node)}
                          className="flex w-full flex-col gap-1 rounded-lg border border-[#e6dcd8] bg-[#f8f1ef] p-2 text-left transition hover:bg-[#eee4e0] dark:border-slate-800 dark:bg-slate-900/80 dark:hover:bg-slate-800/80"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-[11px] font-bold text-[#2f3a46] dark:text-slate-200">
                              {node.topic}
                            </span>
                            <span
                              className="shrink-0 rounded-full px-1.5 text-[9px] text-white"
                              style={{
                                backgroundColor: getNodeColor(node),
                              }}
                            >
                              {getNodePrimaryKeyword(node)}
                            </span>
                          </div>
                          <div className="flex items-center justify-between gap-2 text-[10px] text-[#68717d] dark:text-slate-400">
                            <span>
                              {formatDay(node.createdAt)}{' '}
                              {formatTime(node.createdAt)} ({node.turns})
                            </span>
                            <span className="truncate text-[#8d4660] dark:text-indigo-400">
                              {shared.join(', ')}
                            </span>
                          </div>
                        </button>
                      ))
                    ) : (
                      <p className="text-[11px] italic text-[#83818a] dark:text-slate-500">
                        {t('memories.spacetime.noSharedMemos', {
                          defaultValue: 'No shared related points yet.',
                        })}
                      </p>
                    )}
                  </div>
                  <div className="mt-3 rounded-lg border border-[#e6dcd8] bg-[#f8f1ef] p-2.5 text-[11px] leading-5 text-[#68717d] dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-400">
                    <div className="mb-1 font-bold text-[#45515f] dark:text-slate-200">
                      {t('memories.spacetime.connectionRule', {
                        defaultValue: 'Connection rule',
                      })}
                    </div>
                    {t('memories.spacetime.connectionRuleDescription', {
                      defaultValue:
                        'A curve is drawn when two topics share at least one keyword, alias, or knowledge-base ID. The shared terms shown above are the explanation for the link. Isolated nodes have no shared signal under this rule.',
                    })}
                  </div>
                </div>
                <Button
                  className="mt-3 w-full border-[#d8b9c4] bg-[#f4e9e6] text-[#6d334a] hover:bg-[#ead8d2] dark:border-indigo-800/60 dark:bg-indigo-950/70 dark:text-indigo-200 dark:hover:bg-indigo-900"
                  size="sm"
                  variant="outline"
                  onClick={() => openMemory(selectedNode.primaryMemoryId)}
                >
                  <ExternalLink className="size-4" />
                  {t('memories.spacetime.openMemo', {
                    defaultValue: 'Open memo',
                  })}
                </Button>
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-[#e6dcd8] dark:border-slate-800 px-4 py-8 text-center text-xs text-[#83818a] dark:text-slate-500">
                <MousePointer2 className="mx-auto mb-2 size-8 opacity-50" />
                {t('memories.spacetime.selectHint', {
                  defaultValue: 'Select a circle to inspect this memo.',
                })}
              </div>
            )}
          </div>

          <div className="border-t border-[#e6dcd8] dark:border-slate-800 bg-[#f8f1ef] dark:bg-slate-900/20 p-5">
            <div className="rounded-xl border border-[#e6dcd8] bg-white p-4 dark:border-slate-800 dark:bg-slate-950/80">
              <div className="flex items-start gap-3">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-[#8d4660]/10 text-[#8d4660] dark:bg-indigo-500/10 dark:text-indigo-300">
                  <BrainCircuit className="size-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-bold text-[#2f3a46] dark:text-slate-100">
                    {t('memories.profile.title', {
                      defaultValue: 'Thinking profile',
                    })}
                  </div>
                  <p className="mt-1 text-xs leading-5 text-[#68717d] dark:text-slate-400">
                    {t('memories.profile.entryDescription', {
                      defaultValue:
                        'Open a full page to inspect top topics, learning path, recent changes, and traceable memo evidence.',
                    })}
                  </p>
                  <Button
                    className="mt-3 w-full border-[#d8b9c4] bg-[#f4e9e6] text-[#6d334a] hover:bg-[#ead8d2] dark:border-indigo-800/60 dark:bg-indigo-950/70 dark:text-indigo-200 dark:hover:bg-indigo-900"
                    size="sm"
                    variant="outline"
                    onClick={openProfile}
                    disabled={profileOpening}
                  >
                    {profileOpening ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <BrainCircuit className="size-4" />
                    )}
                    {t('memories.profile.openProfile', {
                      defaultValue: 'Open thinking profile',
                    })}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </aside>

        <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex shrink-0 items-center justify-end border-b border-[#e6dcd8] dark:border-slate-800/80 bg-[#f8f1ef] dark:bg-slate-900 px-4 py-2 text-xs">
            <div className="flex items-center gap-3 text-[11px] text-[#68717d] dark:text-slate-400">
              {keywordLegendItems.length
                ? keywordLegendItems.map(([keyword, count]) => (
                    <span className="flex items-center gap-1" key={keyword}>
                      <span
                        className="size-2.5 rounded-full shadow"
                        style={{ backgroundColor: getKeywordColor(keyword) }}
                      />
                      {keyword} · {count}
                    </span>
                  ))
                : legendItems.map(([category, label]) => (
                    <span className="flex items-center gap-1" key={category}>
                      <span
                        className="size-2.5 rounded-full shadow"
                        style={{ backgroundColor: CATEGORY_COLORS[category] }}
                      />
                      {label}
                    </span>
                  ))}
            </div>
          </div>

          <div
            ref={wrapperRef}
            className="relative min-h-0 flex-1 overflow-hidden bg-[#fbf7f5] dark:bg-[#070b14]"
          >
            {(loading || profileOpening) && (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-white dark:bg-slate-950/60 backdrop-blur-sm">
                <div className="flex flex-col items-center gap-3 rounded-xl border border-[#e6dcd8] bg-white/90 px-5 py-4 text-sm text-[#4f5865] shadow-xl dark:border-slate-800 dark:bg-slate-950/90 dark:text-slate-300">
                  <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" />
                  <span>
                    {profileOpening
                      ? t('memories.profile.openingProfile', {
                          defaultValue: 'Opening thinking profile...',
                        })
                      : t('common.loading', { defaultValue: 'Loading...' })}
                  </span>
                </div>
              </div>
            )}
            {nodes.length ? (
              <>
                <canvas
                  ref={canvasRef}
                  className="block size-full"
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={handleMouseUp}
                  onMouseLeave={handleMouseLeave}
                />
                {hoveredNode && tooltip && (
                  <div
                    className="pointer-events-auto absolute z-30 w-72 rounded-xl border border-[#d8c9c4] dark:border-slate-700/80 bg-[#f8f1ef] dark:bg-slate-900/95 p-3 text-xs shadow-2xl backdrop-blur"
                    style={{
                      left: Math.min(tooltip.x + 16, canvasSize.width - 300),
                      top: Math.min(tooltip.y + 16, canvasSize.height - 220),
                    }}
                  >
                    <div className="mb-2 flex items-start gap-2">
                      <MessageSquareText className="mt-0.5 size-4 shrink-0 text-accent-primary" />
                      <div className="min-w-0">
                        <div className="line-clamp-2 font-semibold text-[#263241] dark:text-slate-100">
                          {hoveredNode.topic}
                        </div>
                        <div className="mt-0.5 text-[#68717d] dark:text-slate-400">
                          {formatDate(hoveredNode.createdAt)} ·{' '}
                          {formatTime(hoveredNode.createdAt)} ·{' '}
                          {hoveredNode.memoryCount}{' '}
                          {t('memories.spacetime.totalMemos', {
                            defaultValue: 'Memos',
                          })}
                        </div>
                      </div>
                    </div>
                    {hoveredNode.preview && (
                      <p className="mb-3 line-clamp-4 whitespace-pre-line text-[#68717d] dark:text-slate-400">
                        {hoveredNode.preview}
                      </p>
                    )}
                    <div className="mb-3 flex flex-wrap gap-1.5">
                      {hoveredNode.keywords.slice(0, 5).map((keyword) => (
                        <span
                          className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-accent-primary"
                          key={keyword}
                        >
                          {keyword}
                        </span>
                      ))}
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full border-[#d8c9c4] bg-white text-[#2f3a46] hover:bg-[#eee4e0] dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-800"
                      onClick={() => openMemory(hoveredNode.primaryMemoryId)}
                    >
                      <ExternalLink className="size-4" />
                      {t('memories.spacetime.openMemo', {
                        defaultValue: 'Open memo',
                      })}
                    </Button>
                  </div>
                )}
                {hoveredRelation && relationTooltip && (
                  <div
                    className="pointer-events-none absolute z-30 w-80 rounded-xl border border-[#d8c9c4] bg-[#f8f1ef] p-3 text-xs shadow-2xl backdrop-blur dark:border-slate-700/80 dark:bg-slate-900/95"
                    style={{
                      left: Math.min(
                        relationTooltip.x + 16,
                        canvasSize.width - 336,
                      ),
                      top: Math.min(
                        relationTooltip.y + 16,
                        canvasSize.height - 240,
                      ),
                    }}
                  >
                    <div className="mb-2 flex items-start gap-2">
                      <GitBranch className="mt-0.5 size-4 shrink-0 text-accent-primary" />
                      <div className="min-w-0">
                        <div className="font-semibold text-[#263241] dark:text-slate-100">
                          {t('memories.spacetime.relationTooltipTitle', {
                            defaultValue: 'Relation explanation',
                          })}
                        </div>
                        <div className="mt-1 line-clamp-2 text-[#68717d] dark:text-slate-400">
                          {hoveredRelation.source.topic} /{' '}
                          {hoveredRelation.target.topic}
                        </div>
                      </div>
                    </div>
                    <div className="mb-2 grid grid-cols-2 gap-2">
                      <div className="rounded-lg border border-[#e6dcd8] bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
                        <span className="block text-[10px] text-[#83818a] dark:text-slate-500">
                          {t('memories.spacetime.relationType', {
                            defaultValue: 'Relation type',
                          })}
                        </span>
                        <span className="font-bold text-[#6d334a] dark:text-indigo-300">
                          {t(
                            `memories.spacetime.relationTypes.${hoveredRelation.relationType}`,
                            {
                              defaultValue: hoveredRelation.relationType,
                            },
                          )}
                        </span>
                      </div>
                      <div className="rounded-lg border border-[#e6dcd8] bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
                        <span className="block text-[10px] text-[#83818a] dark:text-slate-500">
                          {t('memories.spacetime.relationStrength', {
                            defaultValue: 'Strength',
                          })}
                        </span>
                        <span className="font-mono font-bold text-[#6d334a] dark:text-indigo-300">
                          {hoveredRelation.strength}%
                        </span>
                      </div>
                    </div>
                    <p className="mb-2 leading-5 text-[#68717d] dark:text-slate-400">
                      {t('memories.spacetime.relationReason', {
                        terms: hoveredRelation.sharedKeywords
                          .slice(0, 6)
                          .join(', '),
                        defaultValue:
                          'These two memo topics are connected because they share the following extracted signals: {{terms}}.',
                      })}
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {hoveredRelation.sharedKeywords
                        .slice(0, 8)
                        .map((keyword) => (
                          <span
                            className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-accent-primary"
                            key={keyword}
                          >
                            {keyword}
                          </span>
                        ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="flex size-full flex-col items-center justify-center gap-4 p-8 text-center">
                <Network className="size-12 text-[#83818a] dark:text-slate-500" />
                <div>
                  <h3 className="text-lg font-semibold text-[#263241] dark:text-slate-100">
                    {t('memories.spacetime.emptyTitle', {
                      defaultValue: 'No memos to visualize',
                    })}
                  </h3>
                  <p className="mt-2 text-sm text-[#68717d] dark:text-slate-400">
                    {t('memories.spacetime.emptyDescription', {
                      defaultValue:
                        'Create a memo or add a chat session to memo first.',
                    })}
                  </p>
                </div>
                {onCreate && (
                  <Button onClick={onCreate}>
                    {t('memories.createMemory', {
                      defaultValue: 'Create memory',
                    })}
                  </Button>
                )}
              </div>
            )}
          </div>
        </main>
      </div>
    </section>
  );
}
