'use client';

import { AvatarNameDescription } from '@/components/avatar-name-description';
import { KnowledgeBaseFormField } from '@/components/knowledge-base-item';
import { MetadataFilter } from '@/components/metadata-filter';
import { SwitchFormField } from '@/components/switch-fom-field';
import { TavilyFormField } from '@/components/tavily-form-field';
import { TOCEnhanceFormField } from '@/components/toc-enhance-form-field';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { MultiSelect } from '@/components/ui/multi-select';
import { RAGFlowSelect } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useTranslate } from '@/hooks/common-hooks';
import { useFetchKnowledgeMetadataKeys } from '@/hooks/use-knowledge-request';
import { usePanythonTtsEngineSettings } from '@/hooks/use-panython-tts-settings';
import { getDirAttribute } from '@/utils/text-direction';
import { useEffect, useMemo } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

export default function ChatBasicSetting() {
  const { t } = useTranslate('chat');
  const form = useFormContext();
  const { settings: ttsEngineSettings } = usePanythonTtsEngineSettings();
  const emptyResponseValue = form.watch('prompt_config.empty_response');
  const prologueValue = form.watch('prompt_config.prologue');
  const ttsEnabled = useWatch({
    control: form.control,
    name: 'prompt_config.tts',
  });
  const rawDatasetIds = useWatch({
    control: form.control,
    name: 'dataset_ids',
  });
  const kbIds = useMemo(
    () => (rawDatasetIds || []) as string[],
    [rawDatasetIds],
  );
  const metadataInclude = useWatch({
    control: form.control,
    name: 'prompt_config.reference_metadata.include',
  });
  const { data: metadataKeys, loading: metadataKeysLoading } =
    useFetchKnowledgeMetadataKeys(kbIds);
  const metadataFieldOptions = useMemo(() => {
    return (metadataKeys || []).map((key) => ({
      label: key,
      value: key,
    }));
  }, [metadataKeys]);

  useEffect(() => {
    const currentFields = form.getValues(
      'prompt_config.reference_metadata.fields',
    );
    if (
      metadataInclude &&
      Array.isArray(currentFields) &&
      currentFields.length > 0 &&
      metadataKeys
    ) {
      const validFields = currentFields.filter((field) =>
        metadataKeys.includes(field),
      );
      if (validFields.length !== currentFields.length) {
        form.setValue('prompt_config.reference_metadata.fields', validFields);
      }
    } else if (!metadataInclude) {
      form.setValue('prompt_config.reference_metadata.fields', undefined);
    }
  }, [kbIds, metadataKeys, metadataKeysLoading, metadataInclude, form]);

  useEffect(() => {
    if (!ttsEngineSettings.tts_enabled) {
      form.setValue('prompt_config.tts', false);
      return;
    }

    const currentConfig = form.getValues('prompt_config.tts_config') || {};
    form.setValue('prompt_config.tts_config', {
      speed: currentConfig.speed ?? ttsEngineSettings.default_speed,
      emotion: currentConfig.emotion ?? ttsEngineSettings.default_emotion,
      dialect: currentConfig.dialect ?? ttsEngineSettings.default_dialect,
      gender: currentConfig.gender ?? ttsEngineSettings.default_gender,
      voice_profile:
        currentConfig.voice_profile ?? ttsEngineSettings.default_voice_profile,
      sync_caption:
        currentConfig.sync_caption ?? ttsEngineSettings.supports_sync_caption,
    });
  }, [form, ttsEngineSettings]);

  const ttsEmotionOptions = useMemo(
    () => [
      { value: 'professional', label: t('ttsEmotionProfessional') },
      { value: 'calm', label: t('ttsEmotionCalm') },
      { value: 'friendly', label: t('ttsEmotionFriendly') },
      { value: 'formal', label: t('ttsEmotionFormal') },
      { value: 'lively', label: t('ttsEmotionLively') },
      { value: 'serious', label: t('ttsEmotionSerious') },
    ],
    [t],
  );

  const ttsDialectOptions = useMemo(
    () => [
      { value: 'mandarin', label: t('ttsDialectMandarin') },
      { value: 'cantonese', label: t('ttsDialectCantonese') },
      { value: 'sichuan', label: t('ttsDialectSichuan') },
      { value: 'shanghai', label: t('ttsDialectShanghai') },
      { value: 'dongbei', label: t('ttsDialectDongbei') },
      { value: 'minnan', label: t('ttsDialectMinnan') },
    ],
    [t],
  );

  const ttsGenderOptions = useMemo(
    () => [
      { value: 'female', label: t('ttsGenderFemale') },
      { value: 'male', label: t('ttsGenderMale') },
    ],
    [t],
  );

  return (
    <div className="space-y-8">
      <AvatarNameDescription />
      <FormField
        control={form.control}
        name={'prompt_config.empty_response'}
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip={t('emptyResponseTip')}>
              {t('emptyResponse')}
            </FormLabel>
            <FormControl>
              <Textarea
                {...field}
                placeholder={t('emptyResponsePlaceholder')}
                dir={getDirAttribute(emptyResponseValue || '')}
              ></Textarea>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name={'prompt_config.prologue'}
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip={t('setAnOpenerTip')}>
              {t('setAnOpener')}
            </FormLabel>
            <FormControl>
              <Textarea
                {...field}
                dir={getDirAttribute(prologueValue || '')}
              ></Textarea>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <SwitchFormField
        name={'prompt_config.quote'}
        label={t('quote')}
        tooltip={t('quoteTip')}
      ></SwitchFormField>
      <SwitchFormField
        name={'prompt_config.keyword'}
        label={t('keyword')}
        tooltip={t('keywordTip')}
      ></SwitchFormField>
      {ttsEngineSettings.tts_enabled && (
        <div className="space-y-4 rounded-md border-0.5 border-border-card p-3">
          <SwitchFormField
            name={'prompt_config.tts'}
            label={t('tts')}
            tooltip={t('ttsTip')}
          ></SwitchFormField>
          {ttsEnabled && (
            <div className="grid grid-cols-2 gap-3">
              {ttsEngineSettings.supports_speed && (
                <FormField
                  control={form.control}
                  name={'prompt_config.tts_config.speed'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('ttsSpeed')}</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={0.5}
                          max={2}
                          step={0.05}
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
              {ttsEngineSettings.supports_voice_profile && (
                <FormField
                  control={form.control}
                  name={'prompt_config.tts_config.voice_profile'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('ttsVoiceProfile')}</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
              <FormField
                control={form.control}
                name={'prompt_config.tts_config.gender'}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('ttsGender')}</FormLabel>
                    <RAGFlowSelect
                      {...field}
                      FormControlComponent={FormControl}
                      options={ttsGenderOptions}
                      placeholder={t('knowledgeBasesPlaceholder')}
                    />
                    <FormMessage />
                  </FormItem>
                )}
              />
              {ttsEngineSettings.supports_emotion && (
                <FormField
                  control={form.control}
                  name={'prompt_config.tts_config.emotion'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('ttsEmotion')}</FormLabel>
                      <RAGFlowSelect
                        {...field}
                        FormControlComponent={FormControl}
                        options={ttsEmotionOptions}
                        placeholder={t('knowledgeBasesPlaceholder')}
                      />
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
              {ttsEngineSettings.supports_dialect && (
                <FormField
                  control={form.control}
                  name={'prompt_config.tts_config.dialect'}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('ttsDialect')}</FormLabel>
                      <RAGFlowSelect
                        {...field}
                        FormControlComponent={FormControl}
                        options={ttsDialectOptions}
                        placeholder={t('knowledgeBasesPlaceholder')}
                      />
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
              {ttsEngineSettings.supports_sync_caption && (
                <SwitchFormField
                  name={'prompt_config.tts_config.sync_caption'}
                  label={t('ttsSyncCaption')}
                  tooltip={t('ttsSyncCaptionTip')}
                ></SwitchFormField>
              )}
            </div>
          )}
        </div>
      )}
      <TOCEnhanceFormField name="prompt_config.toc_enhance"></TOCEnhanceFormField>
      <TavilyFormField></TavilyFormField>
      <KnowledgeBaseFormField></KnowledgeBaseFormField>
      <MetadataFilter></MetadataFilter>
      <FormField
        control={form.control}
        name={'prompt_config.reference_metadata.include'}
        render={({ field }) => (
          <FormItem className="flex flex-row items-start space-x-3 space-y-0">
            <FormControl>
              <Switch
                checked={field.value}
                onCheckedChange={(value) => {
                  field.onChange(value);
                  if (!value) {
                    form.setValue(
                      'prompt_config.reference_metadata.fields',
                      undefined,
                    );
                  }
                }}
              />
            </FormControl>
            <FormLabel tooltip="Display document metadata (e.g., title, page number, upload date) alongside retrieved text chunks">
              Show chunk metadata
            </FormLabel>
          </FormItem>
        )}
      />
      {metadataInclude && (
        <FormField
          control={form.control}
          name={'prompt_config.reference_metadata.fields'}
          render={({ field }) => (
            <FormItem>
              <FormLabel tooltip="Select which metadata fields to display with each chunk">
                {t('metadataKeys')}
              </FormLabel>
              <FormControl className="bg-bg-input">
                <MultiSelect
                  options={metadataFieldOptions}
                  onValueChange={field.onChange}
                  showSelectAll={false}
                  placeholder="Please select"
                  maxCount={20}
                  defaultValue={Array.isArray(field.value) ? field.value : []}
                  value={Array.isArray(field.value) ? field.value : []}
                  name={field.name}
                  ref={field.ref}
                  onBlur={field.onBlur}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      )}
    </div>
  );
}
