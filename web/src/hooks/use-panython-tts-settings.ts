import request from '@/utils/request';
import { useQuery } from '@tanstack/react-query';

export type PanythonTtsEngineSettings = {
  tts_enabled: boolean;
  engine: string;
  supports_speed: boolean;
  supports_emotion: boolean;
  supports_dialect: boolean;
  supports_voice_profile: boolean;
  supports_sync_caption: boolean;
  default_speed: number;
  default_emotion: string;
  default_dialect: string;
  default_gender: string;
  default_voice_profile: string;
  buffer_ms: number;
  segment_max_chars_zh: number;
  segment_max_words_en: number;
};

export const defaultPanythonTtsEngineSettings: PanythonTtsEngineSettings = {
  tts_enabled: false,
  engine: 'CosyVoice3',
  supports_speed: true,
  supports_emotion: true,
  supports_dialect: true,
  supports_voice_profile: true,
  supports_sync_caption: true,
  default_speed: 1,
  default_emotion: 'professional',
  default_dialect: 'mandarin',
  default_gender: 'female',
  default_voice_profile: 'female_mandarin_01',
  buffer_ms: 1200,
  segment_max_chars_zh: 45,
  segment_max_words_en: 18,
};

export const PanythonTtsSettingsApiAction = {
  FetchEngineSettings: 'fetchPanythonTtsEngineSettings',
};

export function usePanythonTtsEngineSettings() {
  const { data, isFetching: loading } = useQuery({
    queryKey: [PanythonTtsSettingsApiAction.FetchEngineSettings],
    refetchOnWindowFocus: false,
    queryFn: async () => {
      const { data } = await request.get('/api/v1/dev/tts-engine-settings');
      return {
        ...defaultPanythonTtsEngineSettings,
        ...(data?.data ?? {}),
      } as PanythonTtsEngineSettings;
    },
  });

  return {
    settings: data ?? defaultPanythonTtsEngineSettings,
    loading,
  };
}
