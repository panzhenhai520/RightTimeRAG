import { Button } from '@/components/ui/button';
import { Routes } from '@/routes';
import { formatDate } from '@/utils/date';
import {
  BarChart3,
  CalendarDays,
  ExternalLink,
  MessageSquareText,
  Network,
  RotateCcw,
  ZoomIn,
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
  const isDark = document.documentElement.classList.contains('dark');
  const styles = getComputedStyle(document.documentElement);
  const accent = styles.getPropertyValue('--accent-primary').trim();
  const accentColor = accent ? `rgb(${accent})` : '#7c4f63';

  if (isDark) {
    return {
      background: '#172833',
      panel: 'rgba(255,255,255,0.045)',
      grid: 'rgba(220,236,244,0.12)',
      gridStrong: 'rgba(220,236,244,0.24)',
      text: 'rgba(230,239,244,0.88)',
      muted: 'rgba(205,221,229,0.58)',
      accent: '#8fb3c5',
      edge: 'rgba(143,179,197,0.24)',
    };
  }

  return {
    background: '#fbf6f4',
    panel: 'rgba(255,255,255,0.78)',
    grid: 'rgba(118,84,74,0.13)',
    gridStrong: 'rgba(118,84,74,0.26)',
    text: 'rgba(35,38,43,0.84)',
    muted: 'rgba(80,76,75,0.58)',
    accent: accentColor,
    edge: 'rgba(124,79,99,0.2)',
  };
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
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
    roundRect(ctx, plot.left, plot.top, plot.plotWidth, plot.plotHeight, 18);
    ctx.fill();

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

    positioned.forEach((source, sourceIndex) => {
      if (!source.visible) return;
      positioned.slice(sourceIndex + 1).forEach((target) => {
        if (!target.visible) return;
        const shared = sharedKeywordCount(source, target);
        if (!shared) return;
        ctx.strokeStyle = shared > 1 ? theme.accent : theme.edge;
        ctx.globalAlpha = Math.min(0.58, 0.14 + shared * 0.12);
        ctx.lineWidth = Math.min(2.4, 0.7 + shared * 0.45);
        ctx.beginPath();
        ctx.moveTo(source.x, source.y);
        ctx.lineTo(target.x, target.y);
        ctx.stroke();
        ctx.globalAlpha = 1;
      });
    });

    positioned.forEach((node) => {
      if (!node.visible) return;
      const isSelected = node.id === selectedId;
      const isHovered = node.id === hoveredId;
      const color = CATEGORY_COLORS[node.category];

      ctx.shadowColor = isSelected || isHovered ? color : 'transparent';
      ctx.shadowBlur = isSelected || isHovered ? 16 : 0;
      ctx.fillStyle = color;
      ctx.globalAlpha = isSelected || isHovered ? 0.95 : 0.78;
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.shadowBlur = 0;
      ctx.strokeStyle = isSelected ? '#fff' : 'rgba(255,255,255,0.68)';
      ctx.lineWidth = isSelected ? 3 : 1.4;
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
    canvasSize.height,
    canvasSize.width,
    dateOffsetDays,
    hoveredId,
    nodes,
    selectedId,
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
    setFocusDate(new Date().toISOString().slice(0, 10));
  }, []);

  const focusOnDate = useCallback(() => {
    const date = new Date(focusDate);
    if (Number.isNaN(date.getTime())) return;
    const today = getStartOfDay(new Date()).getTime();
    setDateOffsetDays((getStartOfDay(date).getTime() - today) / 86_400_000);
  }, [focusDate]);

  const visibleNodes = positionedRef.current.filter((node) => node.visible);
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

  const denseConnections = useMemo(() => {
    let count = 0;
    nodes.forEach((source, index) => {
      nodes.slice(index + 1).forEach((target) => {
        if (sharedKeywordCount(source, target)) count += 1;
      });
    });
    return count;
  }, [nodes]);

  return (
    <section className="flex min-h-0 flex-1 gap-4 px-5 pb-5">
      <aside className="flex w-[300px] shrink-0 flex-col gap-3 overflow-y-auto rounded-xl border border-border-default/50 bg-bg-base/70 p-4 shadow-sm dark:bg-bg-component/45">
        <div>
          <div className="flex items-center gap-2 text-lg font-semibold text-text-primary">
            <Network className="size-5 text-accent-primary" />
            {t('memories.spacetime.title', {
              defaultValue: 'Memory spacetime',
            })}
          </div>
          <p className="mt-1 text-xs leading-5 text-text-secondary">
            {t('memories.spacetime.subtitle', {
              defaultValue:
                'Topics are placed by creation date and time. Radius reflects conversation turns.',
            })}
          </p>
        </div>

        <div className="rounded-lg bg-bg-card/50 p-3">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-text-primary">
            <BarChart3 className="size-4 text-accent-primary" />
            {t('memories.spacetime.stats', { defaultValue: 'Statistics' })}
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
            <div className="rounded-md bg-bg-base/60 p-2">
              <div>
                {t('memories.spacetime.topics', { defaultValue: 'Topics' })}
              </div>
              <div className="mt-1 text-base font-semibold text-text-primary">
                {nodes.length}
              </div>
            </div>
            <div className="rounded-md bg-bg-base/60 p-2">
              <div>
                {t('memories.spacetime.visible', { defaultValue: 'Visible' })}
              </div>
              <div className="mt-1 text-base font-semibold text-text-primary">
                {visibleNodes.length || nodes.length}
              </div>
            </div>
            <div className="rounded-md bg-bg-base/60 p-2">
              <div>
                {t('memories.spacetime.connections', { defaultValue: 'Links' })}
              </div>
              <div className="mt-1 text-base font-semibold text-text-primary">
                {denseConnections}
              </div>
            </div>
            <div className="rounded-md bg-bg-base/60 p-2">
              <div>
                {t('memories.spacetime.totalMemos', { defaultValue: 'Memos' })}
              </div>
              <div className="mt-1 text-base font-semibold text-text-primary">
                {rawNodes.length}
              </div>
            </div>
          </div>
        </div>

        <MemoProfilePanel
          inputs={profileInputs}
          metrics={profileMetrics}
          trends={profileTrends}
          onOpenMemory={openMemory}
        />

        <div className="rounded-lg bg-bg-card/50 p-3">
          <label className="mb-2 flex items-center gap-2 text-sm font-medium text-text-primary">
            <CalendarDays className="size-4 text-accent-primary" />
            {t('memories.spacetime.focusDate', { defaultValue: 'Focus date' })}
          </label>
          <div className="flex gap-2">
            <input
              type="date"
              value={focusDate}
              onChange={(event) => setFocusDate(event.target.value)}
              className="min-w-0 flex-1 rounded-md border border-border-default/60 bg-bg-base px-2 py-1.5 text-xs text-text-primary outline-none focus:border-accent-primary"
            />
            <Button size="sm" variant="outline" onClick={focusOnDate}>
              <CalendarDays className="size-4 text-accent-primary" />
            </Button>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <ZoomIn className="size-4 text-text-secondary" />
            <input
              aria-label={t('memories.spacetime.zoom', {
                defaultValue: 'Zoom',
              })}
              type="range"
              min="0.55"
              max="2.2"
              step="0.05"
              value={zoom}
              onChange={(event) => setZoom(Number(event.target.value))}
              className="w-full accent-[rgb(var(--accent-primary))]"
            />
            <span className="w-10 text-right text-xs text-text-secondary">
              {Math.round(zoom * 100)}%
            </span>
          </div>
          <Button
            className="mt-3 w-full"
            size="sm"
            variant="outline"
            onClick={resetViewport}
          >
            <RotateCcw className="size-4" />
            {t('memories.spacetime.reset', { defaultValue: 'Reset viewport' })}
          </Button>
        </div>

        <div className="rounded-lg bg-bg-card/50 p-3">
          <div className="mb-2 text-sm font-medium text-text-primary">
            {t('memories.spacetime.keywordAnalysis', {
              defaultValue: 'Keyword connections',
            })}
          </div>
          {topKeywords.length ? (
            <div className="flex flex-wrap gap-2">
              {topKeywords.map(([keyword, count]) => (
                <span
                  key={keyword}
                  className="rounded-full bg-accent-primary/10 px-2.5 py-1 text-xs text-accent-primary"
                >
                  {keyword} · {count}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-text-secondary">
              {t('memories.spacetime.noKeywords', {
                defaultValue: 'No keyword links yet.',
              })}
            </p>
          )}
        </div>

        <div className="min-h-0 flex-1 rounded-lg bg-bg-card/50 p-3">
          <div className="mb-2 text-sm font-medium text-text-primary">
            {t('memories.spacetime.selectedMemo', {
              defaultValue: 'Selected memo',
            })}
          </div>
          {selectedNode ? (
            <div className="space-y-3 text-xs leading-5 text-text-secondary">
              <div>
                <div className="line-clamp-3 text-sm font-semibold text-text-primary">
                  {selectedNode.topic}
                </div>
                <div className="mt-1">
                  {formatDate(selectedNode.createdAt)} · {selectedNode.turns}{' '}
                  {t('memory.sideBar.messages', { defaultValue: 'Messages' })}
                  {' · '}
                  {selectedNode.memoryCount}{' '}
                  {t('memories.spacetime.totalMemos', {
                    defaultValue: 'Memos',
                  })}
                </div>
              </div>
              {selectedNode.aliases.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {selectedNode.aliases.slice(0, 7).map((alias) => (
                    <span
                      className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-accent-primary"
                      key={alias}
                    >
                      {alias}
                    </span>
                  ))}
                </div>
              )}
              {selectedNode.preview && (
                <p className="line-clamp-6 whitespace-pre-line">
                  {selectedNode.preview}
                </p>
              )}
              <div className="flex flex-wrap gap-1.5">
                {selectedNode.keywords.slice(0, 6).map((keyword) => (
                  <span
                    className="rounded-full bg-bg-base px-2 py-0.5"
                    key={keyword}
                  >
                    {keyword}
                  </span>
                ))}
              </div>
              <Button
                className="w-full"
                size="sm"
                onClick={() => openMemory(selectedNode.primaryMemoryId)}
              >
                <ExternalLink className="size-4" />
                {t('memories.spacetime.openMemo', {
                  defaultValue: 'Open memo',
                })}
              </Button>
            </div>
          ) : (
            <p className="text-xs text-text-secondary">
              {t('memories.spacetime.selectHint', {
                defaultValue: 'Select a circle to inspect this memo.',
              })}
            </p>
          )}
        </div>
      </aside>

      <div
        ref={wrapperRef}
        className="relative min-w-0 flex-1 overflow-hidden rounded-xl border border-border-default/45 bg-bg-base shadow-sm dark:bg-bg-component/40"
      >
        {loading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-bg-base/60 backdrop-blur-sm">
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
                className="pointer-events-auto absolute z-30 w-72 rounded-xl border border-border-default/60 bg-bg-base/95 p-3 text-xs shadow-xl backdrop-blur dark:bg-bg-component/95"
                style={{
                  left: Math.min(tooltip.x + 16, canvasSize.width - 300),
                  top: Math.min(tooltip.y + 16, canvasSize.height - 220),
                }}
              >
                <div className="mb-2 flex items-start gap-2">
                  <MessageSquareText className="mt-0.5 size-4 shrink-0 text-accent-primary" />
                  <div className="min-w-0">
                    <div className="line-clamp-2 font-semibold text-text-primary">
                      {hoveredNode.topic}
                    </div>
                    <div className="mt-0.5 text-text-secondary">
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
                  <p className="mb-3 line-clamp-4 whitespace-pre-line text-text-secondary">
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
                  className="w-full"
                  size="sm"
                  variant="outline"
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
            <Network className="size-12 text-text-secondary" />
            <div>
              <h3 className="text-lg font-semibold text-text-primary">
                {t('memories.spacetime.emptyTitle', {
                  defaultValue: 'No memos to visualize',
                })}
              </h3>
              <p className="mt-2 text-sm text-text-secondary">
                {t('memories.spacetime.emptyDescription', {
                  defaultValue:
                    'Create a memo or add a chat session to memo first.',
                })}
              </p>
            </div>
            {onCreate && (
              <Button onClick={onCreate}>
                {t('memories.createMemory', { defaultValue: 'Create memory' })}
              </Button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
