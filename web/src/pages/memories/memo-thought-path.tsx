import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ChatSearchParams } from '@/constants/chat';
import { Routes } from '@/routes';
import {
  BookOpen,
  Clock,
  ExternalLink,
  GitBranch,
  Info,
  Maximize2,
  Network,
  RefreshCw,
  Route,
  Sparkles,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import type {
  DeleteMemoryProfileTopicMergesPayload,
  IMemoThoughtEvent,
  IMemoThoughtProfile,
  MergeMemoryProfileTopicsPayload,
} from './interface';

type MemoThoughtPathProps = {
  profile: IMemoThoughtProfile;
  loading?: boolean;
  refreshing?: boolean;
  onRefresh: () => void;
  onMergeTopic?: (payload: MergeMemoryProfileTopicsPayload) => void;
  onDeleteTopicMerge?: (payload: DeleteMemoryProfileTopicMergesPayload) => void;
  mergingTopic?: boolean;
  deletingTopicMerge?: boolean;
};

const DOMAIN_ORDER = [
  'math',
  'ai',
  'industry',
  'enterprise',
  'finance',
  'law',
  'general',
];

const DOMAIN_COLORS: Record<string, string> = {
  math: '#4f7fb4',
  ai: '#7c6cc7',
  industry: '#5d8c7a',
  enterprise: '#b77955',
  finance: '#b15773',
  law: '#6f7892',
  general: '#8a7f78',
};

const EDGE_LABELS: Record<string, string> = {
  continuation: 'Continuation',
  tool: 'Tool',
  decision: 'Decision',
  evidence: 'Evidence',
  extension: 'Extension',
  bridge: 'Bridge',
  association: 'Association',
};

function formatDate(timestamp: number) {
  if (!timestamp) return '-';
  return new Intl.DateTimeFormat(undefined, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(timestamp));
}

function eventRadius(event: IMemoThoughtEvent) {
  return Math.max(9, Math.min(22, 8 + Math.sqrt(event.turns || 1) * 4));
}

export function MemoThoughtPath({
  profile,
  loading,
  refreshing,
  onRefresh,
  onMergeTopic,
  onDeleteTopicMerge,
  mergingTopic,
  deletingTopicMerge,
}: MemoThoughtPathProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [focusedLane, setFocusedLane] = useState<string | null>(null);
  const [algorithmOpen, setAlgorithmOpen] = useState(false);

  const events = useMemo(() => profile.events ?? [], [profile.events]);
  const edges = useMemo(() => profile.edges ?? [], [profile.edges]);
  const selectedEvent =
    events.find((event) => event.id === selectedEventId) || events.at(-1);
  const selectedEdge = edges.find((edge) => edge.id === selectedEdgeId);
  const mergeSuggestions = useMemo(
    () => profile.topic_merge_suggestions ?? [],
    [profile.topic_merge_suggestions],
  );
  const activeTopicMerges = useMemo(
    () => Object.entries(profile.topic_merges?.rules ?? {}),
    [profile.topic_merges?.rules],
  );

  const topicLabelById = useMemo(() => {
    const labelMap = new Map<string, string>();
    profile.topics.forEach((topic) => {
      labelMap.set(topic.id, topic.label);
      topic.source_topic_ids?.forEach((sourceTopicId) => {
        labelMap.set(sourceTopicId, topic.label);
      });
    });
    events.forEach((event) => {
      labelMap.set(event.topic_id, event.topic_label);
      if (event.original_topic_id && event.original_topic_label) {
        labelMap.set(event.original_topic_id, event.original_topic_label);
      }
    });
    return labelMap;
  }, [events, profile.topics]);

  const lanes = useMemo(() => {
    const present = new Set(events.map((event) => event.domain || 'general'));
    return DOMAIN_ORDER.filter((domain) => present.has(domain)).concat(
      Array.from(present).filter((domain) => !DOMAIN_ORDER.includes(domain)),
    );
  }, [events]);

  const layout = useMemo(() => {
    const laneCounts = lanes.map(
      (domain) =>
        events.filter((event) => (event.domain || 'general') === domain).length,
    );
    const maxLaneCount = Math.max(1, ...laneCounts);
    const width = Math.round(Math.max(1080, 190 + maxLaneCount * 140) * zoom);
    const defaultLaneHeight = focusedLane ? 66 : 92;
    const focusedLaneHeight = 152;
    const top = 44;
    const left = 118;
    const right = 64;
    const laneBands = lanes.map((domain, index) => {
      const previousHeight = lanes
        .slice(0, index)
        .reduce(
          (sum, lane) =>
            sum +
            (focusedLane && lane === focusedLane
              ? focusedLaneHeight
              : defaultLaneHeight),
          0,
        );
      const height =
        focusedLane && domain === focusedLane
          ? focusedLaneHeight
          : defaultLaneHeight;
      return {
        domain,
        y: top + previousHeight,
        height,
        centerY: top + previousHeight + height / 2,
      };
    });
    const bottom = 74;
    const height = Math.max(
      420,
      top + laneBands.reduce((sum, lane) => sum + lane.height, 0) + bottom,
    );
    const minTime = Math.min(
      ...events.map((event) => event.created_at),
      Date.now(),
    );
    const maxTime = Math.max(
      ...events.map((event) => event.created_at),
      minTime + 1,
    );
    const span = Math.max(1, maxTime - minTime);
    const points = new Map<string, { x: number; y: number }>();
    const rawPoints = events.map((event, index) => {
      const lane =
        laneBands.find((item) => item.domain === (event.domain || 'general')) ||
        laneBands[0];
      const timeRatio =
        events.length <= 1
          ? 0.5
          : (event.created_at - minTime) / span ||
            index / Math.max(1, events.length - 1);
      return {
        event,
        x: left + timeRatio * (width - left - right),
        y: lane?.centerY ?? top + 46,
        laneHeight: lane?.height ?? defaultLaneHeight,
      };
    });
    lanes.forEach((domain) => {
      const lanePoints = rawPoints
        .filter(({ event }) => (event.domain || 'general') === domain)
        .sort((a, b) => a.x - b.x);
      let previousX = -Infinity;
      lanePoints.forEach((point, index) => {
        const minSpacing = focusedLane === domain ? 150 : 116;
        const x = Math.max(point.x, previousX + minSpacing);
        previousX = Math.min(x, width - right);
        const offsets =
          focusedLane === domain
            ? [0, -30, 30, -54, 54]
            : [0, -18, 18, -32, 32];
        const y =
          point.y +
          offsets[index % offsets.length] *
            Math.min(1, Math.max(0.55, point.laneHeight / 152));
        points.set(point.event.id, { x: previousX, y });
      });
    });
    return { width, height, laneBands, top, points };
  }, [events, lanes, focusedLane, zoom]);

  const openMemory = (memoryId?: string) => {
    if (!memoryId) return;
    navigate(`${Routes.Memory}${Routes.MemoryMessage}/${memoryId}`);
  };

  const askPrediction = (question: string) => {
    const params = new URLSearchParams();
    params.set(ChatSearchParams.SuggestedQuestion, question);
    navigate(`${Routes.Chats}?${params.toString()}`);
  };

  if (loading) {
    return (
      <div className="flex h-80 items-center justify-center rounded-xl bg-bg-card">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-accent-primary border-t-transparent" />
      </div>
    );
  }

  if (profile.status === 'pending' || profile.status === 'building') {
    return (
      <div className="flex h-96 flex-col items-center justify-center rounded-xl border border-border bg-bg-card text-center">
        <RefreshCw className="mb-4 size-10 animate-spin text-accent-primary" />
        <div className="text-lg font-semibold text-text-primary">
          {t('memories.profile.analysisPending', {
            defaultValue: 'Updating thinking profile',
          })}
        </div>
        <p className="mt-2 max-w-lg text-sm leading-6 text-text-secondary">
          {t('memories.profile.analysisPendingDescription', {
            defaultValue:
              'The page will load the cached profile first. A new profile snapshot is being generated in the background.',
          })}
        </p>
      </div>
    );
  }

  if (!events.length) {
    return (
      <div className="rounded-xl border border-border bg-bg-card p-10 text-center">
        <BookOpen className="mx-auto mb-4 size-10 text-accent-primary" />
        <div className="text-lg font-semibold text-text-primary">
          {t('memories.profile.emptyTitle', {
            defaultValue: 'No profile data yet',
          })}
        </div>
        <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
          {t('memories.profile.emptyDescription', {
            defaultValue:
              'Save chat sessions to memo first, then this page can analyze thinking paths, topics, evidence, and possible next questions.',
          })}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)_300px]">
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-accent-primary">
            <Sparkles className="size-4" />
            {t('memories.profile.currentProfile', {
              defaultValue: 'Current thinking profile',
            })}
          </div>
          <h2 className="text-lg font-semibold leading-7 text-text-primary">
            {profile.summary?.headline}
          </h2>
          <p className="mt-2 line-clamp-3 text-sm leading-6 text-text-secondary">
            {profile.summary?.trajectory}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-text-primary">
            <Network className="size-4 text-accent-primary" />
            {t('memories.profile.focusDomains', {
              defaultValue: 'Focus domains',
            })}
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-2 2xl:grid-cols-3">
            {(profile.summary?.focus_domains ?? []).map((domain) => (
              <div
                key={domain.id}
                className="flex min-h-9 items-center justify-between gap-2 rounded-lg bg-bg-base px-3 py-2 text-sm"
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span
                    className="size-2.5 shrink-0 rounded-[3px]"
                    style={{
                      backgroundColor:
                        DOMAIN_COLORS[domain.id] || DOMAIN_COLORS.general,
                    }}
                  />
                  <span className="truncate text-text-primary">
                    {domain.label}
                  </span>
                </span>
                <span className="shrink-0 font-mono text-xs text-text-secondary">
                  {domain.count}
                </span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-medium text-text-primary">
            <Clock className="size-4 text-accent-primary" />
            {t('memories.profile.snapshot', { defaultValue: 'Snapshot' })}
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm text-text-secondary xl:grid-cols-1">
            <div>
              {t('memories.profile.generatedAt', {
                defaultValue: 'Generated',
              })}
              :{' '}
              {profile.generated_at
                ? formatDate(profile.generated_at * 1000)
                : '-'}
            </div>
            <div>
              {t('memories.profile.eventCount', { defaultValue: 'Events' })}:{' '}
              {profile.event_count}
            </div>
            <div>
              {t('memories.profile.duration', { defaultValue: 'Duration' })}:{' '}
              {profile.duration_ms ?? 0}ms
            </div>
          </div>
          <Button
            variant="outline"
            className="mt-3 w-full"
            disabled={refreshing}
            onClick={onRefresh}
          >
            <RefreshCw
              className={refreshing ? 'size-4 animate-spin' : 'size-4'}
            />
            {t('memories.profile.refresh', {
              defaultValue: 'Refresh analysis',
            })}
          </Button>
        </div>
      </section>

      <section className="grid min-h-[560px] gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="rounded-xl border border-border bg-bg-card p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-base font-semibold text-text-primary">
                <Route className="size-5 text-accent-primary" />
                {t('memories.profile.pathMap', {
                  defaultValue: 'Thinking path map',
                })}
              </div>
              <p className="mt-1 text-xs text-text-secondary">
                {t('memories.profile.pathMapDescription', {
                  defaultValue:
                    'Horizontal axis is time. Vertical lanes are domains. Curves explain how saved memos connect.',
                })}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setZoom((value) => Math.max(0.75, value - 0.25))}
              >
                <ZoomOut className="size-4" />
                {t('memories.profile.zoomOut', { defaultValue: 'Zoom out' })}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setZoom((value) => Math.min(2.5, value + 0.25))}
              >
                <ZoomIn className="size-4" />
                {t('memories.profile.zoomIn', { defaultValue: 'Zoom in' })}
              </Button>
              <Button
                variant={focusedLane ? 'default' : 'outline'}
                size="sm"
                disabled={!selectedEvent}
                onClick={() =>
                  setFocusedLane((value) =>
                    value === selectedEvent?.domain
                      ? null
                      : selectedEvent?.domain || null,
                  )
                }
              >
                <Maximize2 className="size-4" />
                {focusedLane
                  ? t('memories.profile.resetLane', {
                      defaultValue: 'Reset lane',
                    })
                  : t('memories.profile.focusLane', {
                      defaultValue: 'Focus lane',
                    })}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setAlgorithmOpen(true)}
              >
                <Info className="size-4" />
                {t('memories.profile.algorithmSources', {
                  defaultValue: 'Algorithm sources',
                })}
              </Button>
            </div>
          </div>
          <div className="overflow-x-auto overflow-y-hidden rounded-lg bg-bg-base p-3 pb-7">
            <svg
              viewBox={`0 0 ${layout.width} ${layout.height}`}
              className="block max-w-none"
              style={{
                width: layout.width,
                minWidth: layout.width,
                height: layout.height,
              }}
              role="img"
            >
              {layout.laneBands.map((lane, index) => {
                const domain = lane.domain;
                const y = lane.y;
                return (
                  <g key={domain}>
                    <rect
                      x="0"
                      y={y}
                      width={layout.width}
                      height={lane.height}
                      fill={
                        index % 2 === 0
                          ? 'rgba(148, 163, 184, 0.08)'
                          : 'transparent'
                      }
                    />
                    <text
                      x="16"
                      y={lane.centerY + 5}
                      className="fill-text-secondary text-[13px] font-medium"
                    >
                      {events.find((event) => event.domain === domain)
                        ?.domain_label || domain}
                    </text>
                    <line
                      x1="118"
                      x2={layout.width - 32}
                      y1={lane.centerY}
                      y2={lane.centerY}
                      stroke="currentColor"
                      className="text-border"
                      strokeDasharray="5 8"
                      strokeWidth="1"
                    />
                  </g>
                );
              })}

              {edges.map((edge) => {
                const source = layout.points.get(edge.source_event_id);
                const target = layout.points.get(edge.target_event_id);
                if (!source || !target) return null;
                const selected = edge.id === selectedEdgeId;
                const control = Math.max(50, Math.abs(target.x - source.x) / 2);
                return (
                  <path
                    key={edge.id}
                    d={`M ${source.x} ${source.y} C ${source.x + control} ${source.y}, ${target.x - control} ${target.y}, ${target.x} ${target.y}`}
                    fill="none"
                    stroke={selected ? '#b15773' : 'rgba(100,116,139,0.35)'}
                    strokeWidth={selected ? 3 : Math.max(1, edge.weight * 2.2)}
                    className="cursor-pointer transition"
                    onClick={() => {
                      setSelectedEdgeId(edge.id);
                      setSelectedEventId(edge.target_event_id);
                    }}
                  >
                    <title>{edge.reason}</title>
                  </path>
                );
              })}

              {events.map((event) => {
                const point = layout.points.get(event.id);
                if (!point) return null;
                const selected = event.id === selectedEvent?.id;
                const radius = eventRadius(event);
                return (
                  <g
                    key={event.id}
                    className="cursor-pointer"
                    onClick={() => {
                      setSelectedEventId(event.id);
                      setSelectedEdgeId(null);
                    }}
                  >
                    <title>{`${event.title} · ${event.domain_label} · ${formatDate(event.created_at)}`}</title>
                    <circle
                      cx={point.x}
                      cy={point.y}
                      r={radius + (selected ? 5 : 0)}
                      fill={
                        DOMAIN_COLORS[event.domain] || DOMAIN_COLORS.general
                      }
                      opacity={selected ? 0.22 : 0.12}
                    />
                    <circle
                      cx={point.x}
                      cy={point.y}
                      r={radius}
                      fill={
                        DOMAIN_COLORS[event.domain] || DOMAIN_COLORS.general
                      }
                      stroke={selected ? '#fff' : 'rgba(255,255,255,0.75)'}
                      strokeWidth={selected ? 3 : 1.5}
                    />
                    <text
                      x={point.x}
                      y={point.y + radius + 18}
                      textAnchor="middle"
                      className="pointer-events-none fill-text-primary text-[12px] font-medium"
                    >
                      {event.topic_label.length > 10
                        ? `${event.topic_label.slice(0, 10)}...`
                        : event.topic_label}
                    </text>
                    <text
                      x={point.x}
                      y={point.y - radius - 8}
                      textAnchor="middle"
                      className="pointer-events-none fill-text-secondary text-[10px]"
                    >
                      {formatDate(event.created_at)}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        <aside className="rounded-xl border border-border bg-bg-card p-5">
          {selectedEdge ? (
            <div>
              <div className="mb-3 flex items-center gap-2 text-base font-semibold text-text-primary">
                <GitBranch className="size-5 text-accent-primary" />
                {t('memories.profile.edgeEvidence', {
                  defaultValue: 'Connection evidence',
                })}
              </div>
              <div className="rounded-lg bg-bg-base p-3 text-sm text-text-primary">
                {EDGE_LABELS[selectedEdge.type] || selectedEdge.type}
              </div>
              <p className="mt-3 text-sm leading-6 text-text-secondary">
                {selectedEdge.reason}
              </p>
              {!!selectedEdge.shared_signals.length && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {selectedEdge.shared_signals.map((signal) => (
                    <span
                      key={signal}
                      className="rounded-full bg-accent-primary/10 px-2.5 py-1 text-xs text-accent-primary"
                    >
                      {signal}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ) : selectedEvent ? (
            <div>
              <div className="mb-3 text-base font-semibold text-text-primary">
                {selectedEvent.title}
              </div>
              <div className="mb-4 flex flex-wrap gap-2">
                <span className="rounded-full bg-accent-primary/10 px-2.5 py-1 text-xs text-accent-primary">
                  {selectedEvent.domain_label}
                </span>
                <span className="rounded-full bg-bg-base px-2.5 py-1 text-xs text-text-secondary">
                  {selectedEvent.intent_label}
                </span>
                <span className="rounded-full bg-bg-base px-2.5 py-1 text-xs text-text-secondary">
                  {formatDate(selectedEvent.created_at)}
                </span>
              </div>
              <p className="text-sm leading-6 text-text-secondary">
                {selectedEvent.summary}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {selectedEvent.keywords.slice(0, 10).map((keyword) => (
                  <span
                    key={keyword}
                    className="rounded-full border border-border px-2.5 py-1 text-xs text-text-secondary"
                  >
                    {keyword}
                  </span>
                ))}
              </div>
              <Button
                variant="outline"
                className="mt-5 w-full"
                onClick={() => openMemory(selectedEvent.memory_id)}
              >
                <ExternalLink className="size-4" />
                {t('memories.profile.openEvidenceMemo', {
                  defaultValue: 'Open source memo',
                })}
              </Button>
            </div>
          ) : null}

          {!!profile.predictions.length && (
            <div className="mt-5 border-t border-border pt-5">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-primary">
                <Sparkles className="size-4 text-accent-primary" />
                {t('memories.profile.predictedQuestions', {
                  defaultValue: 'Possible next questions',
                })}
              </div>
              <div className="space-y-2">
                {profile.predictions.slice(0, 4).map((prediction, index) => (
                  <button
                    key={`${prediction.question}-${index}`}
                    type="button"
                    className="w-full rounded-lg border border-border bg-bg-base px-3 py-2 text-left text-sm leading-5 text-text-primary transition hover:border-accent-primary hover:bg-accent-primary/5"
                    onClick={() => askPrediction(prediction.question)}
                  >
                    <span className="block font-medium">
                      {prediction.question}
                    </span>
                    <span className="mt-1 line-clamp-2 block text-xs leading-5 text-text-secondary">
                      {prediction.reason}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {!!mergeSuggestions.length && (
            <div className="mt-5 border-t border-border pt-5">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-text-primary">
                <Network className="size-4 text-accent-primary" />
                {t('memories.profile.topicMergeSuggestions', {
                  defaultValue: 'Topic merge suggestions',
                })}
              </div>
              <p className="mb-3 text-xs leading-5 text-text-secondary">
                {t('memories.profile.topicMergeSuggestionsDescription', {
                  defaultValue:
                    'Confirm only when the suggested topics are the same idea in different wording or language.',
                })}
              </p>
              <div className="space-y-2">
                {mergeSuggestions.slice(0, 4).map((suggestion) => (
                  <div
                    key={`${suggestion.target_topic_id}-${suggestion.source_topic_ids.join('-')}`}
                    className="rounded-lg border border-border bg-bg-base p-3"
                  >
                    <div className="text-sm font-medium leading-5 text-text-primary">
                      {suggestion.source_label}
                    </div>
                    <div className="mt-1 text-xs text-text-secondary">
                      {t('memories.profile.mergeTo', {
                        defaultValue: 'Merge to',
                      })}
                      : {suggestion.target_label}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <span className="rounded-full bg-accent-primary/10 px-2 py-0.5 text-xs text-accent-primary">
                        {t('memories.profile.mergeConfidence', {
                          defaultValue: 'Confidence',
                        })}
                        : {Math.round(suggestion.confidence * 100)}%
                      </span>
                      {suggestion.shared_signals.slice(0, 3).map((signal) => (
                        <span
                          key={signal}
                          className="rounded-full border border-border px-2 py-0.5 text-xs text-text-secondary"
                        >
                          {signal}
                        </span>
                      ))}
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-text-secondary">
                      {suggestion.reason}
                    </p>
                    <Button
                      size="sm"
                      className="mt-3 w-full"
                      disabled={mergingTopic || !onMergeTopic}
                      onClick={() =>
                        onMergeTopic?.({
                          source_topic_ids: suggestion.source_topic_ids,
                          target_topic_id: suggestion.target_topic_id,
                          target_label: suggestion.target_label,
                          reason: suggestion.reason,
                        })
                      }
                    >
                      {t('memories.profile.confirmMerge', {
                        defaultValue: 'Confirm merge',
                      })}
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!!activeTopicMerges.length && (
            <div className="mt-5 border-t border-border pt-5">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-text-primary">
                <GitBranch className="size-4 text-accent-primary" />
                {t('memories.profile.activeTopicMerges', {
                  defaultValue: 'Active topic merges',
                })}
              </div>
              <div className="space-y-2">
                {activeTopicMerges.slice(0, 5).map(([sourceTopicId, rule]) => (
                  <div
                    key={sourceTopicId}
                    className="rounded-lg border border-border bg-bg-base p-3"
                  >
                    <div className="text-sm font-medium leading-5 text-text-primary">
                      {topicLabelById.get(sourceTopicId) || sourceTopicId}
                    </div>
                    <div className="mt-1 text-xs leading-5 text-text-secondary">
                      {t('memories.profile.mergeTo', {
                        defaultValue: 'Merge to',
                      })}
                      : {rule.target_label || rule.target_topic_id}
                    </div>
                    {rule.reason && (
                      <p className="mt-2 line-clamp-2 text-xs leading-5 text-text-secondary">
                        {rule.reason}
                      </p>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-3 w-full"
                      disabled={deletingTopicMerge || !onDeleteTopicMerge}
                      onClick={() =>
                        onDeleteTopicMerge?.({
                          source_topic_ids: [sourceTopicId],
                        })
                      }
                    >
                      {t('memories.profile.undoMerge', {
                        defaultValue: 'Undo merge',
                      })}
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </aside>
      </section>

      <Dialog open={algorithmOpen} onOpenChange={setAlgorithmOpen}>
        <DialogContent className="max-h-[82vh] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {t('memories.profile.algorithmSources', {
                defaultValue: 'Algorithm sources and borrowed ideas',
              })}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {profile.algorithm_notes.map((note) => (
              <div key={note.title} className="rounded-lg bg-bg-card p-4">
                <div className="font-medium leading-6 text-text-primary">
                  {note.title}
                </div>
                <div className="mt-1 text-xs text-text-secondary">
                  {note.authors}
                </div>
                <p className="mt-2 text-sm leading-6 text-text-secondary">
                  {note.borrowed}
                </p>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
