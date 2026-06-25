'use client';

import { CrossLanguageFormField } from '@/components/cross-language-form-field';
import { RerankFormFields } from '@/components/rerank';
import { SimilaritySliderFormField } from '@/components/similarity-slider';
import { SwitchFormField } from '@/components/switch-fom-field';
import { TopNFormField } from '@/components/top-n-item';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { RAGFlowSelect } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { UseKnowledgeGraphFormField } from '@/components/use-knowledge-graph-item';
import { useTranslate } from '@/hooks/common-hooks';
import { getDirAttribute } from '@/utils/text-direction';
import { useFormContext } from 'react-hook-form';
import { DynamicVariableForm } from './dynamic-variable';

const MEMORY_MODE_OPTIONS = [
  { label: 'KB优先（默认）', value: 'kb_first' },
  { label: '记忆优先', value: 'memory_first' },
  { label: '忽略记忆', value: 'ignore_memory' },
];

export function ChatPromptEngine() {
  const { t } = useTranslate('chat');
  const form = useFormContext();
  const systemPromptValue = form.watch('prompt_config.system');

  return (
    <div className="space-y-8">
      <FormField
        control={form.control}
        name="prompt_config.system"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('system')}</FormLabel>
            <FormControl>
              <Textarea
                {...field}
                rows={8}
                placeholder={t('systemPlaceholder')}
                className="overflow-y-auto"
                dir={getDirAttribute(systemPromptValue || '')}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <SimilaritySliderFormField isTooltipShown></SimilaritySliderFormField>
      <TopNFormField></TopNFormField>
      <SwitchFormField
        name={'prompt_config.refine_multiturn'}
        label={t('multiTurn')}
        tooltip={t('multiTurnTip')}
      ></SwitchFormField>
      <UseKnowledgeGraphFormField name="prompt_config.use_kg"></UseKnowledgeGraphFormField>
      <RerankFormFields></RerankFormFields>
      <CrossLanguageFormField></CrossLanguageFormField>
      <FormField
        control={form.control}
        name="memory_mode"
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip="kb_first: KB检索后记忆作补充；memory_first: 先查记忆，命中则跳过KB；ignore_memory: 完全不查记忆">
              记忆策略
            </FormLabel>
            <RAGFlowSelect
              {...field}
              FormControlComponent={FormControl}
              options={MEMORY_MODE_OPTIONS}
              placeholder="选择记忆策略"
            />
            <FormMessage />
          </FormItem>
        )}
      />
      <DynamicVariableForm></DynamicVariableForm>
    </div>
  );
}
