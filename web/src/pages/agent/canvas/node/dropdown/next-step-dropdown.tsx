import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { IModalProps } from '@/interfaces/common';
import { useIsPipeline } from '@/pages/agent/hooks/use-is-pipeline';
import { t } from 'i18next';
import { PropsWithChildren, memo, useEffect, useRef } from 'react';
import {
  AccordionOperators,
  PipelineAccordionOperators,
} from './accordion-operators';
import { HideModalContext, OnNodeCreatedContext } from './operator-item-list';

export function InnerNextStepDropdown({
  children,
  hideModal,
  position,
  onNodeCreated,
  nodeId,
}: PropsWithChildren &
  IModalProps<any> & {
    position?: { x: number; y: number };
    onNodeCreated?: (newNodeId: string) => void;
    nodeId?: string;
  }) {
  const dropdownRef = useRef<HTMLDivElement>(null);
  const isPipeline = useIsPipeline();
  const panelWidth = 680;
  const panelHeight = 560;
  const safePosition = position
    ? {
        x:
          typeof window === 'undefined'
            ? position.x
            : Math.max(12, Math.min(position.x, window.innerWidth - panelWidth - 12)),
        y:
          typeof window === 'undefined'
            ? position.y
            : Math.max(12, Math.min(position.y, window.innerHeight - panelHeight - 12)),
      }
    : undefined;

  useEffect(() => {
    if (position && hideModal) {
      const handleKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Escape') {
          hideModal();
        }
      };

      document.addEventListener('keydown', handleKeyDown);

      return () => {
        document.removeEventListener('keydown', handleKeyDown);
      };
    }
  }, [position, hideModal]);

  if (position) {
    return (
      <div
        ref={dropdownRef}
        style={{
          position: 'fixed',
          left: safePosition?.x ?? position.x,
          top: safePosition?.y ?? position.y,
          zIndex: 1000,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="w-[680px] max-w-[calc(100vw-24px)] font-semibold bg-bg-base border border-border rounded-md shadow-lg">
          <div className="px-3 py-2 border-b border-border">
            <div className="text-sm font-medium">{t('flow.nextStep')}</div>
          </div>
          <HideModalContext.Provider value={hideModal}>
            <OnNodeCreatedContext.Provider value={onNodeCreated}>
              {isPipeline ? (
                <PipelineAccordionOperators
                  isCustomDropdown={true}
                  mousePosition={position}
                  nodeId={nodeId}
                ></PipelineAccordionOperators>
              ) : (
                <AccordionOperators
                  isCustomDropdown={true}
                  mousePosition={position}
                  nodeId={nodeId}
                ></AccordionOperators>
              )}
            </OnNodeCreatedContext.Provider>
          </HideModalContext.Provider>
        </div>
      </div>
    );
  }

  return (
    <DropdownMenu
      open={true}
      onOpenChange={(open) => {
        if (!open && hideModal) {
          hideModal();
        }
      }}
    >
      <DropdownMenuTrigger asChild>{children}</DropdownMenuTrigger>
      <DropdownMenuContent
        onClick={(e) => e.stopPropagation()}
        className="w-[680px] max-w-[calc(100vw-24px)] font-semibold"
      >
        <DropdownMenuLabel className="text-xs text-text-primary">
          {t('flow.nextStep')}
        </DropdownMenuLabel>
        <HideModalContext.Provider value={hideModal}>
          {isPipeline ? (
            <PipelineAccordionOperators
              nodeId={nodeId}
            ></PipelineAccordionOperators>
          ) : (
            <AccordionOperators nodeId={nodeId}></AccordionOperators>
          )}
        </HideModalContext.Provider>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export const NextStepDropdown = memo(InnerNextStepDropdown);
