import { Input } from '@/components/originui/input';
import Spotlight from '@/components/spotlight';
import message from '@/components/ui/message';
import { IUserInfo } from '@/interfaces/database/user-setting';
import { Search } from 'lucide-react';
import { Dispatch, SetStateAction } from 'react';
import { useTranslation } from 'react-i18next';
import './index.less';

export default function SearchHome({
  isSearching,
  setIsSearching,
  searchText,
  setSearchText,
  userInfo,
  canSearch,
}: {
  isSearching: boolean;
  setIsSearching: Dispatch<SetStateAction<boolean>>;
  searchText: string;
  setSearchText: Dispatch<SetStateAction<string>>;
  userInfo?: IUserInfo;
  canSearch?: boolean;
  showEmbedLogo?: boolean;
}) {
  // const { data: userInfo } = useFetchUserInfo();
  const { t } = useTranslation();
  return (
    <section className="relative mt-[15vh] flex w-full items-center justify-center transition-all">
      <div className="relative z-10 flex w-full max-w-4xl flex-col items-center justify-center px-8 pt-8">
        <div className="sticky flex w-full transform justify-center text-xl text-primary">
          {!isSearching && <Spotlight className="z-0" />}
          <div className="flex w-full max-w-3xl flex-col items-center justify-center">
            {!isSearching && (
              <>
                <p className="mb-4 transition-opacity">👋 Hi there</p>
                <p className="mb-10 transition-opacity">
                  {userInfo && (
                    <>
                      {t('search.welcomeBack')}, {userInfo.nickname}
                    </>
                  )}
                </p>
              </>
            )}

            <div className="relative w-full ">
              <Input
                placeholder={t('search.searchGreeting')}
                className="delay-700 w-full rounded-full border-border-default/70 bg-bg-base px-5 py-7 pr-14 text-lg text-text-primary shadow-sm"
                value={searchText}
                onKeyUp={(e) => {
                  if (e.key === 'Enter') {
                    if (canSearch === false) {
                      message.warning(t('search.chooseDataset'));
                      return;
                    }
                    setIsSearching(!isSearching);
                  }
                }}
                onChange={(e) => {
                  if (canSearch === false) {
                    message.warning(t('search.chooseDataset'));
                    return;
                  }
                  setSearchText(e.target.value || '');
                }}
              />
              <button
                type="button"
                className="absolute right-2 top-1/2 w-12 -translate-y-1/2 transform rounded-full bg-accent-primary p-2 text-white shadow hover:opacity-90"
                onClick={() => {
                  if (canSearch === false) {
                    message.warning(t('search.chooseDataset'));
                    return;
                  }
                  setIsSearching(!isSearching);
                }}
              >
                <Search size={22} className="m-auto" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
