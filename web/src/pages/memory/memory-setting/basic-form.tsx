import { AvatarUpload } from '@/components/avatar-upload';
import { RAGFlowFormItem } from '@/components/ragflow-form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { t } from 'i18next';
import { z } from 'zod';
export const basicInfoSchema = {
  name: z.string().min(1, { message: t('setting.nameRequired') }),
  avatar: z.string().optional(),
  description: z.string().optional(),
};
export const defaultBasicInfo = { name: '', avatar: '', description: '' };
const labelClassName = '!w-24 shrink-0';
const valueClassName = '!w-auto flex-1';

export const BasicInfo = ({ isChatMemo = false }: { isChatMemo?: boolean }) => {
  return (
    <>
      <RAGFlowFormItem
        name={'name'}
        label={t('memories.name')}
        required={true}
        horizontal={true}
        labelClassName={labelClassName}
        valueClassName={valueClassName}
        // tooltip={field.tooltip}
        // labelClassName={labelClassName || field.labelClassName}
      >
        {(field) => {
          return <Input {...field} disabled={isChatMemo}></Input>;
        }}
      </RAGFlowFormItem>
      <RAGFlowFormItem
        name={'avatar'}
        label={t('memory.config.avatar')}
        required={false}
        horizontal={true}
        labelClassName={labelClassName}
        valueClassName={valueClassName}
        // tooltip={field.tooltip}
        // labelClassName={labelClassName || field.labelClassName}
      >
        {(field) => {
          return <AvatarUpload {...field}></AvatarUpload>;
        }}
      </RAGFlowFormItem>
      <RAGFlowFormItem
        name={'description'}
        label={t('memory.config.description')}
        required={false}
        horizontal={true}
        className="!items-start"
        labelClassName={labelClassName}
        valueClassName={valueClassName}
        // tooltip={field.tooltip}
        // labelClassName={labelClassName || field.labelClassName}
      >
        {(field) => {
          return (
            <Textarea
              {...field}
              autoSize={{ minRows: 3, maxRows: 8 }}
              placeholder={t('memory.config.descriptionPlaceholder')}
            />
          );
        }}
      </RAGFlowFormItem>
    </>
  );
};
