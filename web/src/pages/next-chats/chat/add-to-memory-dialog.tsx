import { Input } from '@/components/ui/input';
import { Modal } from '@/components/ui/modal/modal';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

export function AddToMemoryDialog({
  open,
  loading,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  loading?: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (topic: string) => void;
}) {
  const { t } = useTranslation();
  const [topic, setTopic] = useState('');

  useEffect(() => {
    if (open) {
      setTopic('');
    }
  }, [open]);

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={t('chat.addToMemory')}
      className="border border-border-default shadow-xl"
      size="small"
      confirmLoading={loading}
      maskClosable={!loading}
      okText={t('modal.okText')}
      cancelText={t('modal.cancelText')}
      onOk={() => onSubmit(topic.trim())}
      onCancel={() => onOpenChange(false)}
    >
      <div className="space-y-3 py-1">
        <div className="text-sm leading-6 text-text-secondary">
          {t('chat.addToMemoryTopicPrompt')}
        </div>
        <Input
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          placeholder={t('chat.addToMemoryTopicPlaceholder')}
          autoFocus
        />
      </div>
    </Modal>
  );
}
