import { ConfirmDeleteDialog } from '@/components/confirm-delete-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  useGetChatSearchParams,
  useRemoveSessions,
} from '@/hooks/use-chat-request';
import { IConversation } from '@/interfaces/database/chat';
import api from '@/utils/api';
import request from '@/utils/next-request';
import { BookMarked, Trash2 } from 'lucide-react';
import {
  MouseEventHandler,
  PropsWithChildren,
  useCallback,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { toast } from 'sonner';
import { useChatUrlParams } from '../hooks/use-chat-url';
import { AddToMemoryDialog } from './add-to-memory-dialog';

export function ConversationDropdown({
  children,
  conversation,
  removeTemporaryConversation,
}: PropsWithChildren & {
  conversation: IConversation;
  removeTemporaryConversation?: (conversationId: string) => void;
}) {
  const { t } = useTranslation();
  const { setConversationBoth } = useChatUrlParams();
  const { removeSessions } = useRemoveSessions();
  const { conversationId, isNew } = useGetChatSearchParams();
  const navigate = useNavigate();
  const [addToMemoryOpen, setAddToMemoryOpen] = useState(false);
  const [addToMemoryLoading, setAddToMemoryLoading] = useState(false);

  const openAddToMemoryDialog: MouseEventHandler<HTMLDivElement> = useCallback(
    (e) => {
      e.stopPropagation();
      if (conversation.is_new || !conversation.chat_id || !conversation.id) {
        toast.info(t('chat.addToMemoryPreparing'));
        return;
      }
      setAddToMemoryOpen(true);
    },
    [conversation.chat_id, conversation.id, conversation.is_new, t],
  );

  const handleAddToMemory = useCallback(
    async (topic: string) => {
      setAddToMemoryLoading(true);
      try {
        const { data } = await request.post(api.memorizeChat, {
          chat_id: conversation.chat_id,
          session_id: conversation.id,
          topic,
        });

        if (data?.code === 0) {
          const memoryId = data?.data?.memory_id;
          toast.success(t('chat.addToMemorySuccess'), {
            action: memoryId
              ? {
                  label: t('chat.viewMemory'),
                  onClick: () => navigate(`/memory/message/${memoryId}`),
                }
              : undefined,
          });
          setAddToMemoryOpen(false);
        } else {
          toast.error(data?.message || t('chat.addToMemoryFailed'));
        }
      } catch {
        toast.error(t('chat.addToMemoryFailed'));
      } finally {
        setAddToMemoryLoading(false);
      }
    },
    [conversation.chat_id, conversation.id, navigate, t],
  );

  const handleDelete: MouseEventHandler<HTMLDivElement> =
    useCallback(async () => {
      if (isNew === 'true' && removeTemporaryConversation) {
        removeTemporaryConversation(conversation.id);
        if (conversationId === conversation.id) {
          setConversationBoth('', '');
        }
      } else {
        const code = await removeSessions([conversation.id]);
        if (code === 0) {
          setConversationBoth('', '');
        }
      }
    }, [
      conversation.id,
      conversationId,
      isNew,
      removeSessions,
      removeTemporaryConversation,
      setConversationBoth,
    ]);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>{children}</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem
            onClick={openAddToMemoryDialog}
            data-testid="chat-detail-session-add-memory"
            data-session-id={conversation.id}
          >
            {t('chat.addToMemory')} <BookMarked />
          </DropdownMenuItem>

          <ConfirmDeleteDialog onOk={handleDelete}>
            <DropdownMenuItem
              className="text-state-error"
              onSelect={(e) => {
                e.preventDefault();
              }}
              onClick={(e) => {
                e.stopPropagation();
              }}
              data-testid="chat-detail-session-delete"
              data-session-id={conversation.id}
            >
              {t('common.delete')} <Trash2 />
            </DropdownMenuItem>
          </ConfirmDeleteDialog>
        </DropdownMenuContent>
      </DropdownMenu>
      <AddToMemoryDialog
        open={addToMemoryOpen}
        loading={addToMemoryLoading}
        onOpenChange={setAddToMemoryOpen}
        onSubmit={handleAddToMemory}
      />
    </>
  );
}
