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
import { useDeleteAgent, useSetAgent } from '@/hooks/use-agent-request';
import { IFlow } from '@/interfaces/database/agent';
import { Globe, Lock, PenLine, Tag, Trash2 } from 'lucide-react';
import {
  MouseEventHandler,
  PropsWithChildren,
  useCallback,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { AgentTagEditor } from './agent-tag-editor';
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

  const handleTogglePublish: MouseEventHandler<HTMLDivElement> = useCallback(
    async (e) => {
      e.stopPropagation();
      await setAgent({
        id: agent.id,
        release: agent.release ? 'false' : 'true',
      });
    },
    [agent.id, agent.release, setAgent],
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
          <DropdownMenuItem
            onClick={handleTogglePublish}
            disabled={publishLoading}
          >
            {agent.release ? (
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
                  avatar={{ avatar: agent.avatar, name: agent.title }}
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
