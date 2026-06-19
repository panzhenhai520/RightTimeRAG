import { Button } from '@/components/ui/button';
import message from '@/components/ui/message';
import { usePanythonTtsEngineSettings } from '@/hooks/use-panython-tts-settings';
import { cn } from '@/lib/utils';
import { Volume2, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

const TTS_PLAYBACK_CONSENT_KEY = 'panython.tts.playback.consent.v1';

async function unlockBrowserAudio() {
  const AudioContextConstructor =
    window.AudioContext || (window as any).webkitAudioContext;
  if (AudioContextConstructor) {
    const audioContext = new AudioContextConstructor();
    const source = audioContext.createBufferSource();
    source.buffer = audioContext.createBuffer(1, 1, 22050);
    source.connect(audioContext.destination);
    source.start(0);
    await audioContext.resume();
    window.setTimeout(() => {
      audioContext.close().catch(() => undefined);
    }, 100);
  }

  const audio = new Audio(
    'data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQQAAAAAAA==',
  );
  audio.muted = true;
  audio.volume = 0;
  await audio.play();
  audio.pause();
}

export function TtsPlaybackConsent({
  enabled,
  className,
}: {
  enabled?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  const { settings } = usePanythonTtsEngineSettings();
  const [accepted, setAccepted] = useState(true);

  useEffect(() => {
    setAccepted(window.localStorage.getItem(TTS_PLAYBACK_CONSENT_KEY) === '1');
  }, []);

  const handleEnable = useCallback(async () => {
    try {
      await unlockBrowserAudio();
      window.localStorage.setItem(TTS_PLAYBACK_CONSENT_KEY, '1');
      setAccepted(true);
      message.success(t('chat.ttsPlaybackEnabled'));
    } catch (error) {
      console.warn('Audio unlock failed:', error);
      message.error(t('chat.ttsPlaybackEnableFailed'));
    }
  }, [t]);

  const handleDismiss = useCallback(() => {
    window.localStorage.setItem(TTS_PLAYBACK_CONSENT_KEY, '1');
    setAccepted(true);
  }, []);

  if (!enabled || !settings.tts_enabled || accepted) {
    return null;
  }

  return (
    <div
      className={cn(
        'flex items-center justify-between gap-3 rounded-lg border border-accent-primary/25 bg-accent-primary/10 px-3 py-2 text-sm text-text-primary',
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        <Volume2 className="size-4 shrink-0 text-accent-primary" />
        <span className="min-w-0">{t('chat.ttsPlaybackConsentTip')}</span>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button size="sm" onClick={handleEnable}>
          {t('chat.ttsPlaybackConsentAction')}
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={handleDismiss}
          aria-label={t('common.close')}
          title={t('common.close')}
        >
          <X />
        </Button>
      </div>
    </div>
  );
}
