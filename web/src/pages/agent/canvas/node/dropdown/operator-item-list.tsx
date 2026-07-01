import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Operator } from '@/constants/agent';
import { useFetchAgentOperatorSchema } from '@/hooks/use-agent-request';
import { IModalProps } from '@/interfaces/common';
import { AgentInstanceContext, HandleContext } from '@/pages/agent/context';
import { getNodeGuide, getNodeGuideCategory } from '@/pages/agent/node-guide';
import OperatorIcon from '@/pages/agent/operator-icon';
import { Position } from '@xyflow/react';
import { lowerFirst } from 'lodash';
import { createContext, useContext, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

export type OperatorItemProps = {
  operators: Operator[];
  isCustomDropdown?: boolean;
  mousePosition?: { x: number; y: number };
  query?: string;
  variant?: 'list' | 'card';
};

export const HideModalContext = createContext<IModalProps<any>['showModal']>(
  () => {},
);
export const OnNodeCreatedContext = createContext<
  ((newNodeId: string) => void) | undefined
>(undefined);

export function OperatorItemList({
  operators,
  isCustomDropdown = false,
  mousePosition,
  query = '',
  variant = 'list',
}: OperatorItemProps) {
  const { addCanvasNode } = useContext(AgentInstanceContext);
  const handleContext = useContext(HandleContext);
  const hideModal = useContext(HideModalContext);
  const onNodeCreated = useContext(OnNodeCreatedContext);
  const { t } = useTranslation();
  const { data: operatorManifests } = useFetchAgentOperatorSchema();

  const manifestMap = useMemo(() => {
    return new Map(operatorManifests.map((item) => [item.operator, item]));
  }, [operatorManifests]);

  const visibleOperators = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return operators;
    return operators.filter((operator) => {
      const manifest = manifestMap.get(operator);
      const guide = getNodeGuide(operator);
      const category = getNodeGuideCategory(guide.category);
      const haystack = [
        operator,
        guide.title,
        guide.description,
        category.title,
        category.description,
        t(`flow.${lowerFirst(operator)}`),
        t(`flow.${lowerFirst(operator)}Description`),
        manifest?.category,
        manifest?.risk_level,
        ...(manifest?.requires_service ?? []),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(keyword);
    });
  }, [manifestMap, operators, query, t]);

  const handleClick =
    (operator: Operator): React.MouseEventHandler<HTMLElement> =>
    (e) => {
      const contextData = handleContext || {
        nodeId: '',
        id: '',
        type: 'source' as const,
        position: Position.Right,
        isFromConnectionDrag: true,
      };

      const mockEvent = mousePosition
        ? {
            clientX: mousePosition.x,
            clientY: mousePosition.y,
          }
        : e;

      const newNodeId = addCanvasNode(operator, contextData)(mockEvent);

      if (onNodeCreated && newNodeId) {
        onNodeCreated(newNodeId);
      }

      hideModal?.();
    };

  const renderOperatorItem = (operator: Operator) => {
    const manifest = manifestMap.get(operator);
    const guide = getNodeGuide(operator);
    const category = getNodeGuideCategory(guide.category);
    const services = manifest?.requires_service ?? [];
    const risk = manifest?.risk_level;
    const usesExternal =
      guide.external ||
      services.length > 0 ||
      manifest?.runtime_capabilities?.uses_external_io;
    const riskClass =
      risk === 'high'
        ? 'bg-red-500'
        : risk === 'medium'
          ? 'bg-amber-500'
          : 'bg-emerald-500';
    const badgeClass =
      risk === 'high'
        ? 'border-red-200 bg-red-50 text-red-700'
        : risk === 'medium'
          ? 'border-amber-200 bg-amber-50 text-amber-700'
          : 'border-emerald-200 bg-emerald-50 text-emerald-700';

    if (variant === 'card') {
      return (
        <li key={operator}>
          <button
            type="button"
            onClick={handleClick(operator)}
            className="w-full rounded-md border border-border bg-bg-base p-3 text-left hover:border-accent-primary hover:bg-background-card"
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5 shrink-0 text-text-primary">
                <OperatorIcon name={operator} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="truncate text-sm font-medium text-text-primary">
                    {guide.title}
                  </span>
                  <span className="truncate text-[11px] font-normal text-text-secondary">
                    {operator}
                  </span>
                </div>
                <div className="mt-1 line-clamp-2 text-xs font-normal leading-5 text-text-secondary">
                  {guide.description}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="rounded border border-border px-1.5 py-0.5 text-[11px] font-normal text-text-secondary">
                    {category.title}
                  </span>
                  {usesExternal && (
                    <span className="rounded border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-[11px] font-normal text-sky-700">
                      外部 API/服务
                    </span>
                  )}
                  {manifest && (
                    <span
                      className={`rounded border px-1.5 py-0.5 text-[11px] font-normal ${badgeClass}`}
                    >
                      风险：{risk || 'low'}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </button>
        </li>
      );
    }

    const commonContent = (
      <div className="hover:bg-background-card py-1 px-3 cursor-pointer rounded-sm flex gap-2 items-center justify-start">
        <OperatorIcon name={operator} />
        <span className="truncate flex-1">{guide.title}</span>
        {usesExternal && (
          <span className="rounded bg-sky-50 px-1 text-[10px] font-normal text-sky-700">
            外部
          </span>
        )}
        {manifest && (
          <span className={`size-1.5 rounded-full ${riskClass}`} />
        )}
      </div>
    );

    return (
      <Tooltip key={operator}>
        <TooltipTrigger asChild>
          {isCustomDropdown ? (
            <li onClick={handleClick(operator)}>{commonContent}</li>
          ) : (
            <DropdownMenuItem
              key={operator}
              className="hover:bg-background-card py-1 px-3 cursor-pointer rounded-sm flex gap-2 items-center justify-start"
              onClick={handleClick(operator)}
              onSelect={() => hideModal?.()}
            >
              <OperatorIcon name={operator} />
              <span className="truncate flex-1">
                {guide.title}
              </span>
              {usesExternal && (
                <span className="rounded bg-sky-50 px-1 text-[10px] font-normal text-sky-700">
                  外部
                </span>
              )}
              {manifest && (
                <span className={`size-1.5 rounded-full ${riskClass}`} />
              )}
            </DropdownMenuItem>
          )}
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={24}>
          <div className="max-w-72 space-y-2 text-xs">
            <p>{guide.description}</p>
            {manifest && (
              <div className="space-y-1 text-text-secondary">
                <div>分类：{category.title}</div>
                <div>风险：{manifest.risk_level}</div>
                <div>外部服务：{usesExternal ? services.join(', ') || '需要配置' : '无'}</div>
              </div>
            )}
            {!manifest && (
              <div className="text-text-secondary">
                本地 UI 节点，暂未返回后端执行 schema。
              </div>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    );
  };

  return (
    <ul
      className={
        variant === 'card'
          ? 'max-h-[420px] space-y-2 overflow-auto p-3 text-text-primary font-normal'
          : 'space-y-2 text-text-primary font-normal'
      }
    >
      {visibleOperators.map(renderOperatorItem)}
    </ul>
  );
}
