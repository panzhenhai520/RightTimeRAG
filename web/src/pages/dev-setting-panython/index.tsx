import { Button } from '@/components/ui/button';
import { DEV_FEATURE_SESSION_KEY, Routes } from '@/routes';
import { useEffect } from 'react';
import { Link } from 'react-router';

const devEntries = [
  {
    title: '智能体',
    description: '管理预定义智能体和流程编排。',
    path: Routes.Agents,
  },
  {
    title: '记忆整理',
    description: '管理记忆、消息整理和后续备忘录扩展。',
    path: Routes.Memories,
  },
  {
    title: '文件管理',
    description: '管理系统文件和技能文件。',
    path: Routes.Files,
  },
  {
    title: '配置管理',
    description: '管理数据源和外部连接配置。',
    path: `${Routes.UserSetting}${Routes.DataSource}`,
  },
];

export default function DevSettingPanython() {
  useEffect(() => {
    window.sessionStorage.setItem(DEV_FEATURE_SESSION_KEY, '1');
  }, []);

  return (
    <section className="mx-auto mt-12 max-w-5xl px-4">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-text-primary">
          Panython 开发管理
        </h1>
        <p className="mt-2 text-sm text-text-secondary">
          这些功能用于后台配置，不在普通用户工作台展示。
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {devEntries.map((entry) => (
          <article
            key={entry.path}
            className="rounded-lg border border-border bg-bg-card p-5"
          >
            <h2 className="text-lg font-medium text-text-primary">
              {entry.title}
            </h2>
            <p className="mt-2 min-h-10 text-sm text-text-secondary">
              {entry.description}
            </p>
            <Button asChild className="mt-5 bg-[#6f3f2f] text-white">
              <Link to={entry.path}>打开</Link>
            </Button>
          </article>
        ))}
      </div>
    </section>
  );
}
