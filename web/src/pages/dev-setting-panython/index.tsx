import { Button, ButtonLoading } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useRegister } from '@/hooks/use-login-request';
import { DEV_FEATURE_SESSION_KEY, Routes } from '@/routes';
import { rsaPsw } from '@/utils';
import { FormEvent, useEffect, useState } from 'react';
import { Link } from 'react-router';

const devEntries = [
  {
    title: '新建聊天助手',
    description: '创建并配置聊天助手、模型、提示词和关联知识库。',
    path: `${Routes.Chats}?isCreate=true`,
  },
  {
    title: '新建搜索助手',
    description: '创建并配置搜索助手、搜索范围和结果呈现方式。',
    path: `${Routes.Searches}?isCreate=true`,
  },
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

function RegisterUserCard() {
  const { loading, register } = useRegister();
  const [nickname, setNickname] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const disabled = !nickname.trim() || !email.trim() || !password.trim();

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (disabled) return;

    const code = await register({
      nickname: nickname.trim(),
      email: email.trim(),
      password: rsaPsw(password) as string,
    });

    if (code === 0) {
      setNickname('');
      setEmail('');
      setPassword('');
    }
  };

  return (
    <article className="rounded-lg border border-border bg-bg-card p-5">
      <h2 className="text-lg font-medium text-text-primary">注册用户</h2>
      <p className="mt-2 min-h-10 text-sm text-text-secondary">
        为交付环境创建新用户账户。注册入口仅保留在开发管理页。
      </p>
      <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
        <Input
          value={nickname}
          onChange={(event) => setNickname(event.target.value)}
          placeholder="用户名称"
          autoComplete="username"
        />
        <Input
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="邮箱"
          autoComplete="email"
        />
        <Input
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="密码"
          type="password"
          autoComplete="new-password"
        />
        <ButtonLoading
          type="submit"
          loading={loading}
          disabled={disabled}
          className="mt-2 bg-[#6f3f2f] text-white dark:bg-[#2d5f80]"
        >
          注册用户
        </ButtonLoading>
      </form>
    </article>
  );
}

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
        <RegisterUserCard />
      </div>
    </section>
  );
}
