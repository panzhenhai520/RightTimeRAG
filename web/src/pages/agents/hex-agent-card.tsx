import { MoreButton } from '@/components/more-button';
import { RAGFlowAvatar } from '@/components/ragflow-avatar';
import { Badge } from '@/components/ui/badge';
import { AgentCategory } from '@/constants/agent';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { IFlow } from '@/interfaces/database/agent';
import { cn } from '@/lib/utils';
import React from 'react';
import { AgentDropdown } from './agent-dropdown';
import { useRenameAgent } from './use-rename-agent';

// flat-top regular hexagon — width : height = 2 : √3
export const HEX_W = 210;
export const HEX_H = 182; // 210 * √3/2 ≈ 181.9

// SVG polygon points for a flat-top regular hex in a W×H bounding box
const HEX_POINTS = [
  [HEX_W * 0.25, 0],
  [HEX_W * 0.75, 0],
  [HEX_W, HEX_H * 0.5],
  [HEX_W * 0.75, HEX_H],
  [HEX_W * 0.25, HEX_H],
  [0, HEX_H * 0.5],
]
  .map(([x, y]) => `${x},${y}`)
  .join(' ');

// ─── Hexagon SVG border ────────────────────────────────────────────────────

interface HexBorderProps {
  /** Tailwind color class applied to svg wrapper (uses currentColor on stroke) */
  colorClass: string;
  dashed?: boolean;
  strokeWidth?: number;
}

function HexBorder({
  colorClass,
  dashed = false,
  strokeWidth = 2,
}: HexBorderProps) {
  return (
    <svg
      width={HEX_W}
      height={HEX_H}
      viewBox={`0 0 ${HEX_W} ${HEX_H}`}
      className={cn('absolute inset-0', colorClass)}
    >
      <polygon
        points={HEX_POINTS}
        fill="none"
        stroke="currentColor"
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
        strokeDasharray={dashed ? '10 5' : undefined}
      />
    </svg>
  );
}

// ─── Agent hex card ────────────────────────────────────────────────────────

function AgentTags({ tags }: { tags?: string }) {
  const list = (tags || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
  if (list.length === 0) return null;
  return (
    <>
      {list.slice(0, 2).map((tag) => (
        <Badge
          key={tag}
          variant="secondary"
          className="text-[9px] font-normal px-1 py-0 leading-4"
        >
          {tag}
        </Badge>
      ))}
    </>
  );
}

export type HexAgentCardProps = {
  data: IFlow;
} & Pick<ReturnType<typeof useRenameAgent>, 'showAgentRenameModal'>;

export function HexAgentCard({
  data,
  showAgentRenameModal,
}: HexAgentCardProps) {
  const { navigateToAgent } = useNavigatePage();
  const isPublished = Boolean(data.release_time);

  return (
    // fixed width matches HEX_W so the text area aligns with the hex
    <div
      className="group flex flex-col items-center gap-2"
      style={{ width: HEX_W }}
    >
      {/* hex area */}
      <div
        className="relative cursor-pointer"
        style={{ width: HEX_W, height: HEX_H }}
        onClick={navigateToAgent(
          data?.id,
          data.canvas_category as AgentCategory,
        )}
      >
        {/* border — solid = published, dashed = unpublished */}
        <HexBorder
          dashed={!isPublished}
          colorClass={
            isPublished
              ? 'text-blue-800 dark:text-blue-400'
              : 'text-blue-300 dark:text-blue-600'
          }
        />

        {/* avatar — large, centered inside hex (no fill needed) */}
        <div className="absolute inset-0 flex items-center justify-center">
          <RAGFlowAvatar
            className="h-24 w-24 bg-transparent rounded-full"
            imageClassName="object-cover rounded-full"
            avatar={data.avatar}
            name={data.title}
          />
        </div>

        {/* more button — top-right, revealed on hover */}
        <div
          className="absolute top-5 right-14 z-20 opacity-0 group-hover:opacity-100 transition-opacity duration-150"
          onClick={(e) => e.stopPropagation()}
        >
          <AgentDropdown
            showAgentRenameModal={showAgentRenameModal}
            agent={data}
          >
            <MoreButton />
          </AgentDropdown>
        </div>
      </div>

      {/* text below hex */}
      <div className="flex flex-col items-center gap-1 w-full px-2 text-center">
        <p className="text-sm font-semibold leading-tight line-clamp-2">
          {data.title}
        </p>
        <div className="flex flex-wrap justify-center gap-1">
          {isPublished ? (
            <Badge
              variant="outline"
              className="text-[10px] font-normal border-green-500 text-green-600 dark:border-green-400 dark:text-green-400 px-1.5 py-0"
            >
              已发布
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="text-[10px] font-normal border-orange-400 text-orange-500 dark:border-orange-500 dark:text-orange-400 px-1.5 py-0"
            >
              未发布
            </Badge>
          )}
          <AgentTags tags={data.tags} />
        </div>
      </div>
    </div>
  );
}

// ─── Create-action hex button ──────────────────────────────────────────────

export function HexCreateButton({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
}) {
  return (
    <div
      className="flex flex-col items-center gap-2 cursor-pointer"
      style={{ width: HEX_W }}
      onClick={onClick}
    >
      {/* hex outline only — no fill, no hover color */}
      <div className="relative" style={{ width: HEX_W, height: HEX_H }}>
        <HexBorder
          colorClass="text-gray-300 dark:text-gray-600"
          strokeWidth={1.5}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-text-secondary">{icon}</div>
        </div>
      </div>

      {/* label below hex */}
      <span className="text-sm font-medium text-text-secondary text-center leading-tight px-2">
        {label}
      </span>
    </div>
  );
}
