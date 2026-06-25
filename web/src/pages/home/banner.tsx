import { Card, CardContent } from '@/components/ui/card';
import { ArrowRight, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

function BannerCard() {
  return (
    <Card className="w-auto border-none h-3/4">
      <CardContent className="p-4">
        <span className="inline-block bg-backgroundCoreWeak rounded-sm px-1 text-xs">
          System
        </span>
        <div className="flex mt-1 gap-4">
          <span className="text-lg truncate">Setting up your LLM</span>
          <ArrowRight />
        </div>
      </CardContent>
    </Card>
  );
}

export function Banner() {
  const { t } = useTranslation();

  return (
    <section className="bg-[url('@/assets/banner.png')] bg-cover h-28 rounded-2xl  my-8 flex gap-8 justify-between">
      <div className="h-full text-3xl font-bold items-center inline-flex ml-6">
        {t('homeBanner.welcomeFull')}
      </div>
      <div className="flex justify-between items-center gap-4 mr-5">
        <BannerCard></BannerCard>
        <BannerCard></BannerCard>
        <BannerCard></BannerCard>
        <button
          type="button"
          className="relative p-1 hover:bg-white/10 rounded-full transition-colors"
        >
          <X className="w-6 h-6 text-white" />
        </button>
      </div>
    </section>
  );
}

export function NextBanner() {
  const { i18n, t } = useTranslation();
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <h1
        className="text-5xl leading-normal text-left text-[#163f5d] dark:text-white"
        dir={i18n.language?.startsWith('ar') ? 'rtl' : 'ltr'}
      >
        <span className="font-semibold text-current">
          {t('homeBanner.welcomePrefix')}
        </span>
        <span className="font-bold text-current">
          {t('homeBanner.productName')}
        </span>
      </h1>
      <div className="flex flex-wrap gap-2 pb-1">
        <a
          href="/download/righttime-setup.bat"
          download="righttime-setup.bat"
          className="inline-flex items-center gap-1.5 rounded-md bg-[#6f3f2f]/90 px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-[#6f3f2f] dark:bg-[#2d5f80]/90 dark:hover:bg-[#2d5f80]"
          title={t('homeBanner.setupScriptHint')}
        >
          ⬇ {t('homeBanner.setupScriptBtn')}
        </a>
        <a
          href="/download/righttime-ca.crt"
          download="righttime-ca.crt"
          className="inline-flex items-center gap-1.5 rounded-md border border-[#6f3f2f]/40 px-3 py-1.5 text-xs font-medium text-[#6f3f2f] hover:bg-[#6f3f2f]/10 dark:border-[#9bc7dd]/40 dark:text-[#9bc7dd] dark:hover:bg-[#9bc7dd]/10"
          title={t('homeBanner.certOnlyHint')}
        >
          🔒 {t('homeBanner.certOnlyBtn')}
        </a>
      </div>
    </div>
  );
}
