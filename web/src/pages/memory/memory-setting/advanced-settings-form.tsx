import { FormFieldType, RenderField } from '@/components/dynamic-form';
import { SingleFormSlider } from '@/components/ui/dual-range-slider';
import { NumberInput } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { t } from 'i18next';
import { ListChevronsDownUp, ListChevronsUpDown } from 'lucide-react';
import { useState } from 'react';
import { z } from 'zod';

export const advancedSettingsFormSchema = {
  permissions: z.string().optional(),
  storage_type: z.enum(['table', 'graph']).optional(),
  forgetting_policy: z.enum(['LRU', 'FIFO']).optional(),
  temperature: z.number().optional(),
  system_prompt: z.string().optional(),
  user_prompt: z.string().optional(),
};
export const defaultAdvancedSettingsForm = {
  permissions: '',
  storage_type: '',
  forgetting_policy: '',
  temperature: 0,
  system_prompt: '',
  user_prompt: '',
};
const labelClassName = '!w-24 shrink-0';
export const AdvancedSettingsForm = ({
  defaultOpen = false,
}: {
  defaultOpen?: boolean;
}) => {
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(defaultOpen);
  return (
    <>
      <div
        className={cn('flex items-center gap-1 w-full cursor-pointer', {
          'text-primary': showAdvancedSettings,
        })}
        onClick={() => setShowAdvancedSettings(!showAdvancedSettings)}
      >
        {showAdvancedSettings ? (
          <ListChevronsDownUp size={14} />
        ) : (
          <ListChevronsUpDown size={14} />
        )}
        {t('memory.config.advancedSettings')}
      </div>
      {showAdvancedSettings && (
        <div className="mt-3 grid gap-3">
          <RenderField
            field={{
              name: 'permissions',
              label: t('memory.config.permission'),
              required: false,
              horizontal: true,
              labelClassName,
              // hideLabel: true,
              type: FormFieldType.Custom,
              render: (field) => (
                <RadioGroup
                  defaultValue="me"
                  className="flex gap-4"
                  {...field}
                  onValueChange={(value) => {
                    field.onChange(value);
                  }}
                >
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="me" id="r1" />
                    <Label htmlFor="r1">{t('memory.config.onlyMe')}</Label>
                  </div>
                  <div className="flex items-center gap-2">
                    <RadioGroupItem value="team" id="r2" />
                    <Label htmlFor="r2">{t('memory.config.team')}</Label>
                  </div>
                </RadioGroup>
              ),
            }}
          />
          <RenderField
            field={{
              name: 'storage_type',
              label: t('memory.config.storageType'),
              type: FormFieldType.Select,
              horizontal: true,
              labelClassName,
              placeholder: t('memory.config.storageTypePlaceholder'),
              options: [
                { label: 'Table', value: 'table' },
                // { label: 'Graph', value: 'graph' },
              ],
              required: false,
            }}
          />
          <RenderField
            field={{
              name: 'forgetting_policy',
              label: t('memory.config.forgetPolicy'),
              type: FormFieldType.Select,
              horizontal: true,
              labelClassName,
              // placeholder: t('memory.config.storageTypePlaceholder'),
              options: [
                // { label: 'LRU', value: 'LRU' },
                { label: 'FIFO', value: 'FIFO' },
              ],
              required: false,
            }}
          />
          <RenderField
            field={{
              name: 'temperature',
              label: t('memory.config.temperature'),
              type: FormFieldType.Custom,
              horizontal: true,
              labelClassName,
              required: false,
              render: (field) => (
                <div className="flex gap-2 items-center">
                  <SingleFormSlider
                    {...field}
                    onChange={(value: number) => {
                      field.onChange(value);
                    }}
                    max={1}
                    step={0.01}
                    min={0}
                    disabled={false}
                  ></SingleFormSlider>
                  <NumberInput
                    className={cn(
                      'h-6 w-10 p-1 border border-border-button rounded-sm',
                    )}
                    max={1}
                    step={0.01}
                    min={0}
                    {...field}
                  ></NumberInput>
                </div>
              ),
            }}
          />
          <RenderField
            field={{
              className: '!items-start',
              name: 'system_prompt',
              label: t('memory.config.systemPrompt'),
              type: FormFieldType.Custom,
              horizontal: true,
              labelClassName,
              placeholder: t('memory.config.systemPromptPlaceholder'),
              render: (field) => (
                <Textarea
                  {...field}
                  className="min-h-[190px] text-xs leading-5"
                  placeholder={t('memory.config.systemPromptPlaceholder')}
                />
              ),
              required: false,
            }}
          />
          <RenderField
            field={{
              className: '!items-start',
              name: 'user_prompt',
              label: t('memory.config.userPrompt'),
              type: FormFieldType.Custom,
              horizontal: true,
              labelClassName,
              placeholder: t('memory.config.userPromptPlaceholder'),
              render: (field) => (
                <Textarea
                  {...field}
                  className="min-h-[110px] text-xs leading-5"
                  placeholder={t('memory.config.userPromptPlaceholder')}
                />
              ),
              required: false,
            }}
          />
        </div>
      )}
    </>
  );
};
