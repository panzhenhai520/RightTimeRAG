import { DataFlowSelect } from '@/components/data-pipeline-select';
import { SelectWithSearch } from '@/components/originui/select-with-search';
import { ButtonLoading } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { LanguageTranslationMap } from '@/constants/common';
import { FormLayout } from '@/constants/form';
import { ParseType } from '@/constants/knowledge';
import { useFetchTenantInfo } from '@/hooks/use-user-setting-request';
import { IModalProps } from '@/interfaces/common';
import { zodResolver } from '@hookform/resolvers/zod';
import { omit } from 'lodash';
import { useEffect, useMemo } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import {
  ChunkMethodItem,
  EmbeddingModelItem,
  ParseTypeItem,
} from '../dataset/dataset-setting/configuration/common-item';

const FormId = 'dataset-creating-form';

const ChunkMethodName = 'chunk_method';

export function InputForm({ onOk }: IModalProps<any>) {
  const { t } = useTranslation();
  const { data: tenantInfo } = useFetchTenantInfo();

  const FormSchema = z
    .object({
      name: z
        .string()
        .min(1, {
          message: t('knowledgeList.namePlaceholder'),
        })
        .trim(),
      parseType: z.nativeEnum(ParseType).optional(),
      embedding_model: z
        .string()
        .min(1, {
          message: t('knowledgeConfiguration.embeddingModelPlaceholder'),
        })
        .trim(),
      language: z.string().optional(),
      [ChunkMethodName]: z.string().optional(),
      pipeline_id: z.string().optional(),
    })
    .superRefine((data, ctx) => {
      // When parseType === BuiltIn, chunk_method is required
      if (
        data.parseType === ParseType.BuiltIn &&
        (!data[ChunkMethodName] || data[ChunkMethodName].trim() === '')
      ) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: t('knowledgeList.parserRequired'),
          path: [ChunkMethodName],
        });
      }
      // When parseType === Pipeline, pipeline_id required
      if (data.parseType === ParseType.Pipeline && !data.pipeline_id) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: t('knowledgeList.dataFlowRequired'),
          path: ['pipeline_id'],
        });
      }
    });

  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      name: '',
      parseType: ParseType.BuiltIn,
      [ChunkMethodName]: '',
      embedding_model: tenantInfo?.embd_id,
      language: 'Multilingual/Auto',
    },
  });

  const languageOptions = useMemo(() => {
    return Object.keys(LanguageTranslationMap).map((language) => ({
      label:
        language === 'Multilingual/Auto'
          ? t('language.multilingualAuto')
          : language,
      value: language,
    }));
  }, [t]);

  const parseType = useWatch({
    control: form.control,
    name: 'parseType',
  });

  function onSubmit(data: z.infer<typeof FormSchema>) {
    const nextData =
      parseType === ParseType.BuiltIn ? data : omit(data, ChunkMethodName);
    onOk?.(nextData);
  }

  useEffect(() => {
    if (parseType === ParseType.BuiltIn) {
      form.setValue('pipeline_id', '');
    }
    if (tenantInfo?.embd_id) {
      form.setValue('embedding_model', tenantInfo?.embd_id);
    }
  }, [parseType, form, tenantInfo]);

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit, (errors) => {
          console.warn(errors);
        })}
        className="space-y-6"
        id={FormId}
      >
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                <span className="text-destructive mr-1"> *</span>
                {t('knowledgeList.name')}
              </FormLabel>
              <FormControl>
                <Input
                  placeholder={t('knowledgeList.namePlaceholder')}
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <EmbeddingModelItem line={2} isEdit={false} />
        <FormField
          control={form.control}
          name="language"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('common.language')}</FormLabel>
              <FormControl>
                <SelectWithSearch
                  {...field}
                  options={languageOptions}
                  triggerClassName="w-full"
                  placeholder={t('common.languagePlaceholder')}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <ParseTypeItem />
        {parseType === ParseType.BuiltIn && (
          <ChunkMethodItem name={ChunkMethodName}></ChunkMethodItem>
        )}
        {parseType === ParseType.Pipeline && (
          <DataFlowSelect
            isMult={false}
            showToDataPipeline={true}
            formFieldName="pipeline_id"
            layout={FormLayout.Vertical}
          />
        )}
      </form>
    </Form>
  );
}

export function DatasetCreatingDialog({
  hideModal,
  onOk,
  loading,
}: IModalProps<any>) {
  const { t } = useTranslation();

  return (
    <Dialog open onOpenChange={hideModal}>
      <DialogContent
        className="sm:max-w-[425px] focus-visible:!outline-none flex flex-col"
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            const form = document.getElementById(FormId) as HTMLFormElement;
            form?.requestSubmit();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>{t('knowledgeList.createKnowledgeBase')}</DialogTitle>
        </DialogHeader>
        <DialogDescription></DialogDescription>
        <InputForm onOk={onOk}></InputForm>
        <DialogFooter>
          <ButtonLoading type="submit" form={FormId} loading={loading}>
            {t('common.save')}
          </ButtonLoading>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
