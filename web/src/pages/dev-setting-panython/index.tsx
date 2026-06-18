import { Button, ButtonLoading } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import message from '@/components/ui/message';
import { useRegister } from '@/hooks/use-login-request';
import { DEV_FEATURE_SESSION_KEY, Routes } from '@/routes';
import { rsaPsw } from '@/utils';
import request from '@/utils/next-request';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

const devEntries = [
  {
    titleKey: 'devSettingPanython.createDataset',
    descriptionKey: 'devSettingPanython.createDatasetDescription',
    path: `${Routes.Datasets}?isCreate=true`,
  },
  {
    titleKey: 'devSettingPanython.createChat',
    descriptionKey: 'devSettingPanython.createChatDescription',
    path: `${Routes.Chats}?isCreate=true`,
  },
  {
    titleKey: 'devSettingPanython.createSearch',
    descriptionKey: 'devSettingPanython.createSearchDescription',
    path: `${Routes.Searches}?isCreate=true`,
  },
  {
    titleKey: 'devSettingPanython.agents',
    descriptionKey: 'devSettingPanython.agentsDescription',
    path: Routes.Agents,
  },
  {
    titleKey: 'devSettingPanython.memory',
    descriptionKey: 'devSettingPanython.memoryDescription',
    path: Routes.Memories,
  },
  {
    titleKey: 'devSettingPanython.files',
    descriptionKey: 'devSettingPanython.filesDescription',
    path: Routes.Files,
  },
  {
    titleKey: 'devSettingPanython.configuration',
    descriptionKey: 'devSettingPanython.configurationDescription',
    path: `${Routes.UserSetting}${Routes.DataSource}`,
  },
];

const tenantRelationsApi = '/api/v1/dev/tenant-relations';

type UserRow = {
  id: string;
  email: string;
  nickname: string;
  is_superuser?: boolean;
  status: string;
};

type AssetCounts = Record<string, number>;

type MembershipRow = {
  id: string;
  user_id: string;
  tenant_id: string;
  role: string;
  status: string;
  user_label: string;
  tenant_label: string;
  asset_counts: AssetCounts;
  delete_blockers: string[];
  can_delete: boolean;
};

type DialogOwnerRow = {
  id: string;
  tenant_id: string;
  tenant_label: string;
  name: string;
  llm_id: string;
  tenant_llm_id?: number | null;
  rerank_id?: string;
  tenant_rerank_id?: number | null;
  update_time?: number;
};

type TenantRelationPayload = {
  current_user_id: string;
  users: UserRow[];
  memberships: MembershipRow[];
  dialogs: DialogOwnerRow[];
  asset_counts: Record<string, AssetCounts>;
};

function shortId(id: string) {
  return id ? `${id.slice(0, 8)}...${id.slice(-4)}` : '-';
}

function formatCounts(counts: AssetCounts = {}) {
  const labels: Record<string, string> = {
    datasets: '知识库',
    dialogs: '聊天',
    searches: '搜索',
    agents: '智能体',
    memories: '记忆',
    models: '模型',
  };
  return (
    Object.entries(counts)
      .filter(([, value]) => value > 0)
      .map(([key, value]) => `${labels[key] ?? key}:${value}`)
      .join(' / ') || '无下级资产'
  );
}

function TenantRelationsCard() {
  const [data, setData] = useState<TenantRelationPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [userId, setUserId] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [role, setRole] = useState('normal');
  const [dialogTargets, setDialogTargets] = useState<Record<string, string>>(
    {},
  );

  const loadRelations = useCallback(async () => {
    setLoading(true);
    try {
      const res = await request.get(tenantRelationsApi);
      if (res.data?.code === 0) {
        setData(res.data.data);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRelations();
  }, [loadRelations]);

  const handleUpsertRelation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!userId || !tenantId) return;
    const res = await request.post(tenantRelationsApi, {
      user_id: userId,
      tenant_id: tenantId,
      role,
    });
    if (res.data?.code === 0) {
      setData(res.data.data);
      message.success('租户关系已保存');
    }
  };

  const handleDeleteRelation = async (relation: MembershipRow) => {
    const blockers = relation.delete_blockers || [];
    if (blockers.length > 0) {
      window.alert(
        `不能删除该上级关系，仍存在下级资产：${blockers.join(' / ')}`,
      );
      return;
    }
    if (
      !window.confirm(
        `确认删除 ${relation.user_label} -> ${relation.tenant_label} 的关系？该操作会影响该用户可见范围。`,
      )
    ) {
      return;
    }
    const res = await request.delete(`${tenantRelationsApi}/${relation.id}`);
    if (res.data?.code === 0) {
      setData(res.data.data);
      message.success('租户关系已删除');
    }
  };

  const handleTransferDialog = async (dialog: DialogOwnerRow) => {
    const targetTenantId = dialogTargets[dialog.id];
    if (!targetTenantId || targetTenantId === dialog.tenant_id) return;
    if (
      !window.confirm(
        `确认把聊天助手「${dialog.name}」迁移到目标租户 ${shortId(targetTenantId)}？`,
      )
    ) {
      return;
    }
    const res = await request({
      url: `${tenantRelationsApi}/dialogs/${dialog.id}/tenant`,
      method: 'put',
      data: { tenant_id: targetTenantId },
    });
    if (res.data?.code === 0) {
      setData(res.data.data);
      message.success('聊天助手归属已调整');
    }
  };

  const users = data?.users ?? [];
  const memberships = data?.memberships ?? [];
  const dialogs = data?.dialogs ?? [];

  return (
    <article className="rounded-lg border border-border bg-bg-card p-5 md:col-span-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-text-primary">
            租户关系维护
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            查看用户、租户、聊天助手归属关系。删除上级关系前必须先清空或迁移下级资产。
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            当前用户 ID：{shortId(data?.current_user_id ?? '')}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          loading={loading}
          onClick={loadRelations}
        >
          刷新
        </Button>
      </div>

      <form
        className="mt-5 grid gap-3 rounded-md bg-bg-base/60 p-3 md:grid-cols-[1fr_1fr_120px_auto]"
        onSubmit={handleUpsertRelation}
      >
        <select
          className="h-9 rounded-md bg-bg-input px-3 text-sm outline-none"
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
        >
          <option value="">选择用户</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.nickname || user.email} / {shortId(user.id)}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md bg-bg-input px-3 text-sm outline-none"
          value={tenantId}
          onChange={(event) => setTenantId(event.target.value)}
        >
          <option value="">选择租户</option>
          {users.map((user) => (
            <option key={user.id} value={user.id}>
              {user.nickname || user.email} / {shortId(user.id)}
            </option>
          ))}
        </select>
        <select
          className="h-9 rounded-md bg-bg-input px-3 text-sm outline-none"
          value={role}
          onChange={(event) => setRole(event.target.value)}
        >
          <option value="normal">normal</option>
          <option value="admin">admin</option>
          <option value="owner">owner</option>
        </select>
        <Button type="submit" disabled={!userId || !tenantId}>
          保存关系
        </Button>
      </form>

      <section className="mt-6">
        <h3 className="mb-2 text-sm font-semibold text-text-primary">
          用户-租户关系
        </h3>
        <div className="overflow-x-auto rounded-md border border-border/60">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-bg-base text-text-secondary">
              <tr>
                <th className="px-3 py-2">用户</th>
                <th className="px-3 py-2">租户</th>
                <th className="px-3 py-2">角色</th>
                <th className="px-3 py-2">状态</th>
                <th className="px-3 py-2">下级资产</th>
                <th className="px-3 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {memberships.map((item) => (
                <tr key={item.id} className="border-t border-border/40">
                  <td className="px-3 py-2">
                    <div>{item.user_label}</div>
                    <div className="text-text-secondary" title={item.user_id}>
                      {shortId(item.user_id)}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div>{item.tenant_label}</div>
                    <div className="text-text-secondary" title={item.tenant_id}>
                      {shortId(item.tenant_id)}
                    </div>
                  </td>
                  <td className="px-3 py-2">{item.role}</td>
                  <td className="px-3 py-2">
                    {item.status === '1' ? '有效' : '已删除'}
                  </td>
                  <td className="px-3 py-2">
                    {formatCounts(item.asset_counts)}
                  </td>
                  <td className="px-3 py-2">
                    <Button
                      size="xs"
                      variant="danger"
                      disabled={item.status !== '1' || !item.can_delete}
                      title={
                        item.can_delete
                          ? '删除关系'
                          : `仍有下级资产：${item.delete_blockers.join(' / ')}`
                      }
                      onClick={() => handleDeleteRelation(item)}
                    >
                      删除
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-6">
        <h3 className="mb-2 text-sm font-semibold text-text-primary">
          聊天助手归属
        </h3>
        <div className="overflow-x-auto rounded-md border border-border/60">
          <table className="min-w-full text-left text-xs">
            <thead className="bg-bg-base text-text-secondary">
              <tr>
                <th className="px-3 py-2">助手</th>
                <th className="px-3 py-2">当前租户</th>
                <th className="px-3 py-2">模型</th>
                <th className="px-3 py-2">迁移到</th>
                <th className="px-3 py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {dialogs.map((dialog) => (
                <tr key={dialog.id} className="border-t border-border/40">
                  <td className="px-3 py-2">
                    <div>{dialog.name}</div>
                    <div className="text-text-secondary" title={dialog.id}>
                      {shortId(dialog.id)}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <div>{dialog.tenant_label}</div>
                    <div
                      className="text-text-secondary"
                      title={dialog.tenant_id}
                    >
                      {shortId(dialog.tenant_id)}
                    </div>
                  </td>
                  <td className="max-w-[260px] truncate px-3 py-2">
                    <div title={dialog.llm_id}>{dialog.llm_id || '-'}</div>
                    <div className="text-text-secondary">
                      chat #{dialog.tenant_llm_id ?? '-'} / rerank #
                      {dialog.tenant_rerank_id ?? '-'}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <select
                      className="h-8 min-w-[180px] rounded-md bg-bg-input px-2 text-xs outline-none"
                      value={dialogTargets[dialog.id] ?? ''}
                      onChange={(event) =>
                        setDialogTargets((previous) => ({
                          ...previous,
                          [dialog.id]: event.target.value,
                        }))
                      }
                    >
                      <option value="">选择目标租户</option>
                      {users.map((user) => (
                        <option key={user.id} value={user.id}>
                          {user.nickname || user.email} / {shortId(user.id)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={
                        !dialogTargets[dialog.id] ||
                        dialogTargets[dialog.id] === dialog.tenant_id
                      }
                      onClick={() => handleTransferDialog(dialog)}
                    >
                      迁移
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </article>
  );
}

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
  const { t } = useTranslation();

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
              {t(entry.titleKey)}
            </h2>
            <p className="mt-2 min-h-10 text-sm text-text-secondary">
              {t(entry.descriptionKey)}
            </p>
            <Button asChild className="mt-5 bg-[#6f3f2f] text-white">
              <Link to={entry.path}>打开</Link>
            </Button>
          </article>
        ))}
        <RegisterUserCard />
        <TenantRelationsCard />
      </div>
    </section>
  );
}
