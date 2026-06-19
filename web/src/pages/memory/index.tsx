import Spotlight from '@/components/spotlight';
import { Outlet } from 'react-router';
import { SideBar } from './sidebar';

export default function DatasetWrapper() {
  return (
    <section className="flex h-full w-full flex-col px-5 py-3">
      <SideBar />
      <div className="mt-4 flex min-h-0 flex-1">
        <div className="relative mb-5 flex-1 overflow-auto rounded-xl bg-bg-base/70 p-5 shadow-sm ring-1 ring-border-default/20 dark:bg-bg-component/45">
          <Spotlight />
          <Outlet />
        </div>
      </div>
    </section>
  );
}
