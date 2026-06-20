import { Button } from '@/components/ui/button';
import { Routes } from '@/routes';
import { formatDate } from '@/utils/date';
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  GitBranch,
  Info,
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
  getMemoryTopicText,
  inferCanonicalTopic,
} from './canonical-topic';
import { IMemory } from './interface';
import {
  buildMemoProfileInputs,
  buildMemoProfileMetrics,
  buildMemoTopicTrends,
} from './memo-profile';
import { MemoProfilePanel } from './memo-profile-panel';
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
  grid: string;
  gridStrong: string;
  text: string;
  muted: string;
  accent: string;
  edge: string;
};

const CATEGORY_COLORS: Record<MemoCategory, string> = {
  raw: '#9b6b55',
  semantic: '#4d7fa4',
  episodic: '#b78b45',
  procedural: '#7d6fb0',
  memo: '#7c4f63',
};

const DAY_WIDTH = 92;
const ONE_DAY_MS = 86_400_000;

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
  const canonicalTopic = inferCanonicalTopic(textForKeywords || topic);
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
  const accentColor = accent ? `rgb(${accent})` : '#6366f1';

  return {
    background: '#070b14',
    panel: 'rgba(15,23,42,0.36)',
    grid: 'rgba(71,85,105,0.34)',
    gridStrong: 'rgba(99,102,241,0.38)',
    text: 'rgba(226,232,240,0.9)',
    muted: 'rgba(148,163,184,0.72)',
    accent: accentColor,
    edge: 'rgba(148,163,184,0.08)',
  };
}

function sharedKeywordCount(a: MemoSpacetimeNode, b: MemoSpacetimeNode) {
  const bKeywords = new Set(b.keywords);
  return a.keywords.filter((keyword) => bKeywords.has(keyword)).length;
}

function formatDay(date: Date) {
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function formatTime(date: Date) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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

function calcPositionedNodes(
  nodes: MemoSpacetimeNode[],
  width: number,
  height: number,
  zoom: number,
  dateOffsetDays: number,
) {
  const left = 76;
  const top = 58;
  const right = 28;
  const bottom = 44;
  const plotWidth = Math.max(1, width - left - right);
  const plotHeight = Math.max(1, height - top - bottom);
  const centerDate = getVisibleCenterDate(dateOffsetDays);
  const centerTime = centerDate.getTime();
  const dayWidth = DAY_WIDTH * zoom;

  const positioned = nodes.map((node) => {
    const nodeDay = getStartOfDay(node.createdAt);
    const dayDiff = (nodeDay.getTime() - centerTime) / 86_400_000;
    const minutes =
      node.createdAt.getHours() * 60 + node.createdAt.getMinutes();
    const x = left + plotWidth / 2 + dayDiff * dayWidth;
    const y = top + (minutes / 1440) * plotHeight;
    const radius = Math.max(9, Math.min(30, 7 + Math.sqrt(node.turns) * 4));
    const visible =
      x > left - radius &&
      x < width - right + radius &&
      y > top - radius &&
      y < height - bottom + radius;

    return { ...node, x, y, radius, visible };
  });

  return {
    positioned,
    plot: { left, top, right, bottom, plotWidth, plotHeight },
  };
}

type MemoSpacetimeNetworkProps = {
  memories: IMemory[];
  loading?: boolean;
  onCreate?: () => void;
};

export function MemoSpacetimeNetwork({
  memories,
  loading,
  onCreate,
}: MemoSpacetimeNetworkProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const positionedRef = useRef<PositionedNode[]>([]);
  const dragRef = useRef({ dragging: false, lastX: 0 });
  const [canvasSize, setCanvasSize] = useState({ width: 960, height: 620 });
  const [zoom, setZoom] = useState(1);
  const [dateOffsetDays, setDateOffsetDays] = useState(0);
  const [themeVersion, setThemeVersion] = useState(0);
  const [hoveredId, setHoveredId] = useState<string>();
  const [tooltip, setTooltip] = useState<{ x: number; y: number }>();
  const [selectedId, setSelectedId] = useState<string>();
  const [focusDate, setFocusDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
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
  const profileInputs = useMemo(
    () => buildMemoProfileInputs(memories),
    [memories],
  );
  const profileMetrics = useMemo(
    () => buildMemoProfileMetrics(profileInputs),
    [profileInputs],
  );
  const profileTrends = useMemo(
    () => buildMemoTopicTrends(profileInputs),
    [profileInputs],
  );

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
        shared: selectedNode.keywords.filter((keyword) =>
          node.keywords.includes(keyword),
        ),
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
      node.keywords.forEach((keyword) => {
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
    if (!activeKeyword && !selectedId && !hoveredId) return;
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
  }, [activeKeyword, hoveredId, selectedId]);

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

    const { positioned, plot } = calcPositionedNodes(
      nodes,
      canvasSize.width,
      canvasSize.height,
      zoom,
      dateOffsetDays,
    );
    positionedRef.current = positioned;

    ctx.fillStyle = theme.panel;
    ctx.fillRect(plot.left, plot.top, plot.plotWidth, plot.plotHeight);

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
    for (let hour = 0; hour <= 24; hour += 3) {
      const y = plot.top + (hour / 24) * plot.plotHeight;
      ctx.beginPath();
      ctx.moveTo(plot.left, y);
      ctx.lineTo(canvasSize.width - plot.right, y);
      ctx.stroke();
      ctx.fillStyle = hour % 6 === 0 ? theme.text : theme.muted;
      ctx.font = '12px Inter, sans-serif';
      ctx.fillText(`${String(hour).padStart(2, '0')}:00`, 14, y + 4);
    }

    const centerDate = getVisibleCenterDate(dateOffsetDays);
    const dayWidth = DAY_WIDTH * zoom;
    const visibleDayCount = Math.ceil(plot.plotWidth / dayWidth / 2) + 1;
    for (let day = -visibleDayCount; day <= visibleDayCount; day += 1) {
      const x = plot.left + plot.plotWidth / 2 + day * dayWidth;
      const date = addDays(centerDate, day);
      ctx.strokeStyle = day === 0 ? theme.gridStrong : theme.grid;
      ctx.beginPath();
      ctx.moveTo(x, plot.top);
      ctx.lineTo(x, canvasSize.height - plot.bottom);
      ctx.stroke();
      ctx.fillStyle = day === 0 ? theme.accent : theme.muted;
      ctx.font =
        day === 0 ? '600 12px Inter, sans-serif' : '12px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(formatDay(date), x, 34);
    }
    ctx.textAlign = 'left';

    const activeNodeId = hoveredId || selectedId;
    positioned.forEach((source, sourceIndex) => {
      if (!source.visible) return;
      positioned.slice(sourceIndex + 1).forEach((target) => {
        if (!target.visible) return;
        const shared = sharedKeywordCount(source, target);
        if (!shared) return;
        const isNodeActive =
          activeNodeId &&
          (source.id === activeNodeId || target.id === activeNodeId);
        const isKeywordActive =
          activeKeyword &&
          source.keywords.includes(activeKeyword) &&
          target.keywords.includes(activeKeyword);
        const isActive = isNodeActive || isKeywordActive;
        ctx.strokeStyle = isActive ? '#6366f1' : theme.edge;
        ctx.globalAlpha = isActive
          ? 0.84
          : Math.min(0.16, 0.05 + shared * 0.04);
        ctx.lineWidth = isActive ? 2.4 : 1;
        if (isActive) {
          ctx.setLineDash([7, 9]);
          ctx.lineDashOffset = dashOffset;
          ctx.shadowColor = '#4f46e5';
          ctx.shadowBlur = 9;
        } else {
          ctx.setLineDash([]);
          ctx.shadowBlur = 0;
        }
        ctx.beginPath();
        ctx.moveTo(source.x, source.y);
        if (Math.abs(source.x - target.x) < 2) {
          const midY = (source.y + target.y) / 2;
          const offset = -Math.min(80, Math.abs(source.y - target.y) * 0.35);
          ctx.quadraticCurveTo(source.x + offset, midY, target.x, target.y);
        } else {
          const midX = (source.x + target.x) / 2;
          ctx.bezierCurveTo(midX, source.y, midX, target.y, target.x, target.y);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.shadowBlur = 0;
        ctx.globalAlpha = 1;
      });
    });

    positioned.forEach((node) => {
      if (!node.visible) return;
      const isSelected = node.id === selectedId;
      const isHovered = node.id === hoveredId;
      const color = CATEGORY_COLORS[node.category];

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
          ? '#e0e7ff'
          : 'rgba(255,255,255,0.68)';
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
        setDateOffsetDays((current) => current - deltaX / (DAY_WIDTH * zoom));
        return;
      }

      const node = findNode(point.x, point.y);
      setHoveredId(node?.id);
      setTooltip(node ? { x: point.x, y: point.y } : undefined);
      event.currentTarget.style.cursor = node ? 'pointer' : 'grab';
    },
    [findNode, getCanvasPoint, zoom],
  );

  const handleMouseDown = useCallback(
    (event: ReactMouseEvent<HTMLCanvasElement>) => {
      const point = getCanvasPoint(event);
      const node = findNode(point.x, point.y);
      if (node) {
        setSelectedId(node.id);
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

  const handleWheel = useCallback(
    (event: React.WheelEvent<HTMLCanvasElement>) => {
      event.preventDefault();
      if (event.ctrlKey || event.metaKey) {
        setZoom((current) =>
          Math.min(2.2, Math.max(0.55, current - event.deltaY * 0.0015)),
        );
      } else {
        setDateOffsetDays((current) => current + event.deltaY / 360);
      }
    },
    [],
  );

  const openMemory = useCallback(
    (id: string) => {
      navigate(`${Routes.Memory}${Routes.MemoryMessage}/${id}`);
    },
    [navigate],
  );

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
      node.keywords.forEach((keyword) => {
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

  return (
    <section className="mx-5 mb-5 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-slate-800 bg-[#070b14] text-slate-100 shadow-2xl">
      <header className="flex shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900 px-6 py-3">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-gradient-to-tr from-indigo-500 via-blue-600 to-purple-600 shadow-lg shadow-indigo-500/20">
            <Network className="size-6 text-white" />
          </div>
          <div>
            <h2 className="text-xl font-extrabold tracking-wide text-slate-100">
              {t('memories.spacetime.title', {
                defaultValue: 'Memory spacetime',
              })}
            </h2>
            <p className="text-xs text-slate-400">
              {t('memories.spacetime.subtitle', {
                defaultValue:
                  'Topics are placed by creation date and time. Radius reflects conversation turns.',
              })}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button
            size="sm"
            variant="outline"
            className="border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700"
            onClick={resetViewport}
          >
            <RotateCcw className="size-4" />
            {t('memories.spacetime.reset', { defaultValue: 'Reset viewport' })}
          </Button>
          <div className="rounded-md border border-slate-800 bg-slate-950 px-3 py-1.5 text-xs text-slate-500">
            {t('memories.spacetime.loaded', {
              defaultValue: 'Memory center loaded',
            })}
            : <span className="font-bold text-indigo-400">{nodes.length}</span>{' '}
            {t('memories.spacetime.nodes', { defaultValue: 'nodes' })}
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="flex w-96 shrink-0 flex-col overflow-y-auto border-r border-slate-800 bg-slate-900 shadow-2xl">
          <div className="border-b border-slate-800 p-5">
            <h3 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <span className="size-1.5 rounded-full bg-indigo-500" />
              {t('memories.spacetime.viewportControls', {
                defaultValue: 'Viewport dimensions and panning',
              })}
            </h3>
            <div className="mb-4">
              <label className="mb-2 block text-[11px] text-slate-400">
                {t('memories.spacetime.horizontalPan', {
                  defaultValue:
                    'Horizontal date panning. You can also drag the canvas.',
                })}
              </label>
              <div className="grid grid-cols-5 gap-1">
                <button
                  type="button"
                  onClick={() => shiftDays(-6)}
                  className="flex items-center justify-center gap-1 rounded border border-slate-700/80 bg-slate-800 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-700"
                >
                  <SkipBack className="size-3.5" />
                  -6d
                </button>
                <button
                  type="button"
                  onClick={() => shiftDays(-1)}
                  className="flex items-center justify-center gap-1 rounded border border-slate-700/80 bg-slate-800 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-700"
                >
                  <ChevronLeft className="size-3.5" />
                  -1d
                </button>
                <button
                  type="button"
                  onClick={() => shiftDays(0, true)}
                  className="rounded border border-indigo-800/80 bg-indigo-950/60 py-1.5 text-xs font-bold text-indigo-300 transition hover:bg-indigo-900/70"
                >
                  {t('memories.spacetime.firstDay', {
                    defaultValue: 'First',
                  })}
                </button>
                <button
                  type="button"
                  onClick={() => shiftDays(1)}
                  className="flex items-center justify-center gap-1 rounded border border-slate-700/80 bg-slate-800 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-700"
                >
                  +1d
                  <ChevronRight className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => shiftDays(6)}
                  className="flex items-center justify-center gap-1 rounded border border-slate-700/80 bg-slate-800 py-1.5 text-xs font-medium text-slate-300 transition hover:bg-slate-700"
                >
                  +6d
                  <SkipForward className="size-3.5" />
                </button>
              </div>
            </div>
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label className="text-xs font-medium text-slate-400">
                  {t('memories.spacetime.globalZoom', {
                    defaultValue: 'Proportional canvas zoom',
                  })}
                </label>
                <span className="font-mono text-xs font-bold text-indigo-400">
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
                className="h-1.5 w-full cursor-pointer appearance-none rounded-lg bg-slate-800 accent-indigo-500"
              />
              <div className="mt-1 flex justify-between text-[10px] text-slate-500">
                <span>50%</span>
                <span className="text-indigo-500">100%</span>
                <span>250%</span>
              </div>
            </div>
          </div>

          <div className="border-b border-slate-800 bg-slate-900/40 p-5">
            <h3 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              {t('memories.spacetime.spacetimeClues', {
                defaultValue: 'Spacetime clues',
              })}
            </h3>
            <div className="space-y-4">
              <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3 transition hover:border-slate-700">
                <label className="mb-1 block text-[10px] text-slate-500">
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
                    className="min-w-0 flex-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-center font-mono text-xs font-bold text-white outline-none transition hover:bg-slate-800 focus:border-indigo-500"
                  />
                  <button
                    type="button"
                    onClick={focusOnDate}
                    className="rounded-lg border border-indigo-800/60 bg-indigo-950/50 p-2 text-indigo-300 transition hover:bg-indigo-900/70"
                  >
                    <LocateFixed className="size-4" />
                  </button>
                </div>
                {dateFocusReport && (
                  <div
                    className={
                      dateFocusReport.hasNodes
                        ? 'mt-3.5 space-y-2.5 rounded-xl border border-indigo-500/25 bg-indigo-950/45 p-3.5 text-xs'
                        : 'mt-3.5 space-y-1.5 rounded-xl border border-slate-800/80 bg-slate-950 p-3.5 text-xs text-slate-400'
                    }
                  >
                    <div className="flex items-center gap-1.5 border-b border-indigo-900/40 pb-1.5 font-bold text-indigo-300">
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
                        <div className="grid grid-cols-2 gap-2 text-slate-300">
                          <div className="rounded border border-indigo-800/20 bg-indigo-950/20 p-2">
                            <span className="block text-[9px] text-slate-500">
                              {t('memories.spacetime.memoryFrequency', {
                                defaultValue: 'Memo frequency',
                              })}
                            </span>
                            <span className="font-mono text-sm font-bold text-white">
                              {dateFocusReport.nodeCount}
                            </span>
                          </div>
                          <div className="rounded border border-indigo-800/20 bg-indigo-950/20 p-2">
                            <span className="block text-[9px] text-slate-500">
                              {t('memories.spacetime.totalTurns', {
                                defaultValue: 'Total turns',
                              })}
                            </span>
                            <span className="font-mono text-sm font-bold text-white">
                              {dateFocusReport.turnCount}
                            </span>
                          </div>
                        </div>
                        <div className="space-y-1 text-[11px] leading-normal text-slate-400">
                          <div>
                            {t('memories.spacetime.containsCategories', {
                              defaultValue: 'Categories',
                            })}
                            :{' '}
                            <span className="font-bold text-indigo-200">
                              {dateFocusReport.categories.join(', ')}
                            </span>
                          </div>
                          <div>
                            {t('memories.spacetime.timeSpan', {
                              defaultValue: 'Time span',
                            })}
                            :{' '}
                            <span className="font-bold text-indigo-200">
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

              <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-3 transition hover:border-slate-700">
                <span className="mb-1 block text-xs font-bold text-indigo-400">
                  {t('memories.spacetime.keywordClues', {
                    defaultValue: 'Keyword horizontal clues',
                  })}
                </span>
                <p className="mb-2.5 text-[10px] leading-normal text-slate-400">
                  {t('memories.spacetime.keywordCluesDescription', {
                    defaultValue:
                      'Cluster overlapping keywords across time and locate the strongest similar circuit.',
                  })}
                </p>
                <button
                  type="button"
                  onClick={analyzeKeywordConnections}
                  className="flex w-full items-center justify-center gap-1 rounded border border-indigo-500/30 bg-indigo-500/10 py-1.5 text-xs font-bold text-indigo-300 transition hover:bg-indigo-500/20"
                >
                  <GitBranch className="size-3.5" />
                  {t('memories.spacetime.analyzeGlobalWeave', {
                    defaultValue: 'Analyze global strongest weave',
                  })}
                </button>
                {keywordWeaveReport ? (
                  <div className="mt-3.5 space-y-2.5 rounded-xl border border-indigo-500/25 bg-indigo-950/45 p-3.5 text-xs">
                    <div className="flex items-center gap-1.5 border-b border-indigo-900/40 pb-1.5 font-bold text-indigo-300">
                      <Share2 className="size-3.5" />
                      {t('memories.spacetime.horizontalReport', {
                        defaultValue: 'Horizontal clue report',
                      })}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="mr-1 block text-[10px] text-slate-400">
                        {t('memories.spacetime.strongTies', {
                          defaultValue: 'Strong ties',
                        })}
                        :
                      </span>
                      {keywordWeaveReport.topKeywords.map(
                        ([keyword, count]) => (
                          <span
                            key={keyword}
                            className="rounded border border-indigo-500/30 bg-indigo-950/60 px-2 py-0.5 font-mono text-[10px] font-bold text-indigo-300"
                          >
                            {keyword} ({count})
                          </span>
                        ),
                      )}
                    </div>
                    <div className="space-y-1.5 text-[11px] text-slate-300">
                      <p>
                        {t('memories.spacetime.subnetwork', {
                          defaultValue: 'Related subnetwork',
                        })}
                        :{' '}
                        <span className="font-mono text-sm font-bold text-white">
                          {keywordWeaveReport.connectedCount}
                        </span>
                      </p>
                      <p>
                        {t('memories.spacetime.horizontalSpan', {
                          defaultValue: 'Horizontal time span',
                        })}
                        :{' '}
                        <span className="font-mono text-sm font-bold text-white">
                          {keywordWeaveReport.daySpan}
                        </span>
                      </p>
                    </div>
                    <p className="border-t border-indigo-900/40 pt-1 text-[10px] italic leading-normal text-slate-400">
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
                        className="rounded-full bg-indigo-950/50 px-2 py-0.5 text-[10px] text-indigo-300"
                      >
                        {keyword} · {count}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="mt-3 text-xs italic text-slate-500">
                    {t('memories.spacetime.noKeywords', {
                      defaultValue: 'No keyword links yet.',
                    })}
                  </p>
                )}
              </div>
            </div>
          </div>

          <div className="flex-grow p-5">
            <h3 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <span className="size-1.5 rounded-full bg-purple-500" />
              {t('memories.spacetime.selectedPointInfo', {
                defaultValue: 'Selected memory point',
              })}
            </h3>
            {selectedNode ? (
              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 shadow-xl shadow-indigo-950/20">
                <div className="mb-3 flex items-start justify-between">
                  <span
                    className="rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white"
                    style={{
                      backgroundColor: CATEGORY_COLORS[selectedNode.category],
                    }}
                  >
                    {selectedNode.memoryTypeLabel}
                  </span>
                  <span className="font-mono text-xs text-slate-500">
                    ID: {selectedNode.primaryMemoryId.slice(0, 8)}
                  </span>
                </div>
                <h4 className="mb-2.5 line-clamp-3 text-sm font-bold leading-snug text-slate-200">
                  {selectedNode.topic}
                </h4>
                <div className="mb-3 grid grid-cols-2 gap-2 rounded-lg border border-slate-800/80 bg-slate-900/60 p-2.5 text-xs">
                  <div>
                    <span className="block text-[10px] text-slate-500">
                      {t('memories.spacetime.createdDate', {
                        defaultValue: 'Date',
                      })}
                    </span>
                    <span className="font-mono font-bold text-slate-300">
                      {formatInputDate(selectedNode.createdAt)}
                    </span>
                  </div>
                  <div>
                    <span className="block text-[10px] text-slate-500">
                      {t('memories.spacetime.exactTime', {
                        defaultValue: 'Time',
                      })}
                    </span>
                    <span className="font-mono font-bold text-slate-300">
                      {formatTime(selectedNode.createdAt)}
                    </span>
                  </div>
                </div>
                <div className="mb-3.5">
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="flex items-center gap-1 text-slate-400">
                      <MessageSquareText className="size-3.5 text-indigo-400" />
                      {t('memories.spacetime.turnsScale', {
                        defaultValue: 'Conversation turns',
                      })}
                    </span>
                    <span className="font-mono font-bold text-indigo-400">
                      {selectedNode.turns}
                    </span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500"
                      style={{
                        width: `${Math.min(100, (selectedNode.turns / 20) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
                <div className="mb-4">
                  <span className="mb-1.5 block text-[10px] text-slate-500">
                    {t('memories.spacetime.coreKeywords', {
                      defaultValue: 'Core keywords',
                    })}
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedNode.keywords.slice(0, 10).map((keyword) => (
                      <span
                        key={keyword}
                        className="rounded border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 text-[11px] text-slate-300"
                      >
                        # {keyword}
                      </span>
                    ))}
                  </div>
                </div>
                {selectedNode.preview && (
                  <p className="mb-4 line-clamp-5 whitespace-pre-line rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 text-xs leading-5 text-slate-400">
                    {selectedNode.preview}
                  </p>
                )}
                <div className="border-t border-slate-800 pt-3">
                  <span className="mb-2 flex items-center gap-1 text-[10px] font-bold text-slate-400">
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
                          className="flex w-full flex-col gap-1 rounded-lg border border-slate-800 bg-slate-900/80 p-2 text-left transition hover:bg-slate-800/80"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="truncate text-[11px] font-bold text-slate-200">
                              {node.topic}
                            </span>
                            <span
                              className="shrink-0 rounded-full px-1.5 text-[9px] text-white"
                              style={{
                                backgroundColor: CATEGORY_COLORS[node.category],
                              }}
                            >
                              {node.memoryTypeLabel}
                            </span>
                          </div>
                          <div className="flex items-center justify-between gap-2 text-[10px] text-slate-400">
                            <span>
                              {formatDay(node.createdAt)}{' '}
                              {formatTime(node.createdAt)} ({node.turns})
                            </span>
                            <span className="truncate text-indigo-400">
                              {shared.join(', ')}
                            </span>
                          </div>
                        </button>
                      ))
                    ) : (
                      <p className="text-[11px] italic text-slate-500">
                        {t('memories.spacetime.noSharedMemos', {
                          defaultValue: 'No shared related points yet.',
                        })}
                      </p>
                    )}
                  </div>
                </div>
                <Button
                  className="mt-3 w-full border-indigo-800/60 bg-indigo-950/70 text-indigo-200 hover:bg-indigo-900"
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
              <div className="rounded-lg border border-dashed border-slate-800 px-4 py-8 text-center text-xs text-slate-500">
                <MousePointer2 className="mx-auto mb-2 size-8 opacity-50" />
                {t('memories.spacetime.selectHint', {
                  defaultValue: 'Select a circle to inspect this memo.',
                })}
              </div>
            )}
          </div>

          <div className="border-t border-slate-800 bg-slate-900/20 p-5">
            <MemoProfilePanel
              inputs={profileInputs}
              metrics={profileMetrics}
              trends={profileTrends}
              onOpenMemory={openMemory}
            />
          </div>
        </aside>

        <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
          <div className="flex shrink-0 items-center justify-between border-b border-slate-800/80 bg-slate-900 px-4 py-2 text-xs">
            <span className="flex items-center gap-1.5 text-slate-400">
              <Info className="size-4 text-indigo-400" />
              {t('memories.spacetime.canvasTip', {
                defaultValue:
                  'Mouse wheel pans the time axis. Drag blank space to move dates. Ctrl/Command + wheel zooms.',
              })}
            </span>
            <div className="flex items-center gap-3 text-[11px] text-slate-400">
              {legendItems.map(([category, label]) => (
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
            className="relative min-h-0 flex-1 overflow-hidden bg-[#070b14]"
          >
            {loading && (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/60 backdrop-blur-sm">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" />
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
                  onMouseLeave={handleMouseUp}
                  onWheel={handleWheel}
                />
                {hoveredNode && tooltip && (
                  <div
                    className="pointer-events-auto absolute z-30 w-72 rounded-xl border border-slate-700/80 bg-slate-900/95 p-3 text-xs shadow-2xl backdrop-blur"
                    style={{
                      left: Math.min(tooltip.x + 16, canvasSize.width - 300),
                      top: Math.min(tooltip.y + 16, canvasSize.height - 220),
                    }}
                  >
                    <div className="mb-2 flex items-start gap-2">
                      <MessageSquareText className="mt-0.5 size-4 shrink-0 text-accent-primary" />
                      <div className="min-w-0">
                        <div className="line-clamp-2 font-semibold text-slate-100">
                          {hoveredNode.topic}
                        </div>
                        <div className="mt-0.5 text-slate-400">
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
                      <p className="mb-3 line-clamp-4 whitespace-pre-line text-slate-400">
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
                      className="w-full border-slate-700 bg-slate-950 text-slate-200 hover:bg-slate-800"
                      onClick={() => openMemory(hoveredNode.primaryMemoryId)}
                    >
                      <ExternalLink className="size-4" />
                      {t('memories.spacetime.openMemo', {
                        defaultValue: 'Open memo',
                      })}
                    </Button>
                  </div>
                )}
              </>
            ) : (
              <div className="flex size-full flex-col items-center justify-center gap-4 p-8 text-center">
                <Network className="size-12 text-slate-500" />
                <div>
                  <h3 className="text-lg font-semibold text-slate-100">
                    {t('memories.spacetime.emptyTitle', {
                      defaultValue: 'No memos to visualize',
                    })}
                  </h3>
                  <p className="mt-2 text-sm text-slate-400">
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
