import { MoreButton } from '@/components/more-button';
import { AgentCategory } from '@/constants/agent';
import { useNavigatePage } from '@/hooks/logic-hooks/navigate-hooks';
import { IFlow } from '@/interfaces/database/agent';
import { cn } from '@/lib/utils';
import React from 'react';
import { AgentDropdown } from './agent-dropdown';
import { useHomeAgentSelection } from './hooks/use-home-agent-selection';
import styles from './index.module.less';
import { useRenameAgent } from './use-rename-agent';

export type HexAgentCardProps = {
  data: IFlow;
} & Pick<ReturnType<typeof useRenameAgent>, 'showAgentRenameModal'>;

export function HexTile({
  children,
}: React.PropsWithChildren<{ index: number }>) {
  return <div className={styles.hexTile}>{children}</div>;
}

export function HexAgentCard({
  data,
  showAgentRenameModal,
}: HexAgentCardProps) {
  const { navigateToAgent } = useNavigatePage();
  const { isHomeAgent } = useHomeAgentSelection();
  const isPublished = Boolean(data.release_time);
  const pinnedToHome = isHomeAgent(data.id);

  return (
    <div
      className={cn(styles.hexCell, styles.hexAgent, {
        [styles.hexPublished]: isPublished,
        [styles.hexUnpublished]: !isPublished,
      })}
    >
      <button
        type="button"
        className={styles.hexButton}
        onClick={navigateToAgent(
          data?.id,
          data.canvas_category as AgentCategory,
        )}
      >
        <span className={styles.hexTitle}>{data.title}</span>
        {pinnedToHome && <span className={styles.hexHomeLabel}>首页</span>}
      </button>

      <div
        className={styles.hexMenu}
        onClick={(event) => event.stopPropagation()}
      >
        <AgentDropdown showAgentRenameModal={showAgentRenameModal} agent={data}>
          <MoreButton className={styles.hexMoreButton} />
        </AgentDropdown>
      </div>
    </div>
  );
}

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
    <button
      type="button"
      className={cn(styles.hexCell, styles.hexCreate)}
      onClick={onClick}
    >
      <span className={styles.hexCreateIcon}>{icon}</span>
      <span className={styles.hexTitle}>{label}</span>
    </button>
  );
}

export function HexEmptyCell() {
  return <div className={cn(styles.hexCell, styles.hexEmpty)} />;
}
