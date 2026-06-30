import {
  ConfirmDeleteDialog,
  ConfirmDeleteDialogNode,
} from '@/components/confirm-delete-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { resolveAgentAvatar } from '@/constants/agent';
import { useDeleteAgent, useSetAgent } from '@/hooks/use-agent-request';
import { IFlow } from '@/interfaces/database/agent';
import { Globe, Home, Lock, PenLine, Tag, Trash2 } from 'lucide-react';
import {
  MouseEventHandler,
  PropsWithChildren,
  useCallback,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { AgentTagEditor } from './agent-tag-editor';
import { useHomeAgentSelection } from './hooks/use-home-agent-selection';
import { useRenameAgent } from './use-rename-agent';

export function AgentDropdown({
  children,
  showAgentRenameModal,
  agent: agent,
}: PropsWithChildren &
  Pick<ReturnType<typeof useRenameAgent>, 'showAgentRenameModal'> & {
    agent: IFlow;
  }) {
  const { t } = useTranslation();
  const { deleteAgent } = useDeleteAgent();
  const { loading: publishLoading, setAgent } = useSetAgent(false);
  const { isHomeAgent, toggleHomeAgent } = useHomeAgentSelection();
  const [tagEditorOpen, setTagEditorOpen] = useState(false);

  const handleShowAgentRenameModal: MouseEventHandler<HTMLDivElement> =
    useCallback(
      (e) => {
        e.stopPropagation();
        showAgentRenameModal(agent);
      },
      [agent, showAgentRenameModal],
    );

  const handleEditTags: MouseEventHandler<HTMLDivElement> = useCallback((e) => {
    e.stopPropagation();
    setTagEditorOpen(true);
  }, []);

  const isPublished = Boolean(agent.release_time);
  const isPinnedToHome = isHomeAgent(agent.id);

  const handleToggleHomeAgent: MouseEventHandler<HTMLDivElement> = useCallback(
    (e) => {
      e.stopPropagation();
      toggleHomeAgent(agent);
    },
    [agent, toggleHomeAgent],
  );

  const handleTogglePublish: MouseEventHandler<HTMLDivElement> = useCallback(
    async (e) => {
      e.stopPropagation();
      await setAgent({
        id: agent.id,
        release: isPublished ? 'false' : 'true',
      });
    },
    [agent.id, isPublished, setAgent],
  );

  const handleDelete: MouseEventHandler<HTMLDivElement> = useCallback(() => {
    deleteAgent(agent.id);
  }, [agent.id, deleteAgent]);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>{children}</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onClick={handleShowAgentRenameModal}>
            {t('common.rename')} <PenLine />
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleEditTags}>
            {t('flow.editTags')} <Tag />
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleToggleHomeAgent}>
            {isPinnedToHome ? '取消首页显示' : '设为首页显示'} <Home />
          </DropdownMenuItem>
          <DropdownMenuItem
            onClick={handleTogglePublish}
            disabled={publishLoading}
          >
            {isPublished ? (
              <>
                {t('flow.unpublish') || '取消发布'} <Lock />
              </>
            ) : (
              <>
                {t('flow.publish') || '发布'} <Globe />
              </>
            )}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <ConfirmDeleteDialog
            onOk={handleDelete}
            title={t('deleteModal.delAgent')}
            content={{
              node: (
                <ConfirmDeleteDialogNode
                  avatar={{
                    avatar: resolveAgentAvatar(agent.avatar),
                    name: agent.title,
                  }}
                  name={agent.title}
                />
              ),
            }}
          >
            <DropdownMenuItem
              className="text-state-error"
              onSelect={(e) => {
                e.preventDefault();
              }}
              onClick={(e) => {
                e.stopPropagation();
              }}
            >
              {t('common.delete')} <Trash2 />
            </DropdownMenuItem>
          </ConfirmDeleteDialog>
        </DropdownMenuContent>
      </DropdownMenu>
      <AgentTagEditor
        agent={agent}
        open={tagEditorOpen}
        onOpenChange={setTagEditorOpen}
      />
    </>
  );
}
