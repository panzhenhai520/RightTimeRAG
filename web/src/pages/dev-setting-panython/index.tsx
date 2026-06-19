import { Button, ButtonLoading } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import message from '@/components/ui/message';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
const ttsEngineSettingsApi = '/api/v1/dev/tts-engine-settings';

type TtsEngineSettings = {
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

const defaultTtsEngineSettings: TtsEngineSettings = {
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

const ttsEmotionOptions = [
  ['professional', '专业'],
  ['calm', '平静'],
  ['friendly', '亲切'],
  ['formal', '正式'],
  ['lively', '活泼'],
  ['serious', '严肃'],
];

const ttsDialectOptions = [
  ['mandarin', '普通话'],
  ['cantonese', '粤语/广东话'],
  ['sichuan', '四川'],
  ['shanghai', '上海'],
  ['dongbei', '东北'],
  ['minnan', '闽南'],
  ['tianjin', '天津'],
  ['shandong', '山东'],
];

const ttsVoiceProfileOptions = [
  ['female_mandarin_01', '女声 / 普通话 / 标准'],
  ['male_mandarin_01', '男声 / 普通话 / 标准'],
  ['female_cantonese_01', '女声 / 粤语 / 标准'],
  ['male_cantonese_01', '男声 / 粤语 / 标准'],
  ['female_english_01', '女声 / 英语 / 标准'],
  ['male_english_01', '男声 / 英语 / 标准'],
];

const ttsEngineOptions = [
  ['CosyVoice3', 'CosyVoice 3'],
  ['CosyVoice2', 'CosyVoice 2'],
];

const ttsSpeedOptions = [
  [0.8, '偏慢 0.8x'],
  [1, '正常 1.0x'],
  [1.15, '稍快 1.15x'],
  [1.3, '较快 1.3x'],
];

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
  description?: string;
  llm_id: string;
  tenant_llm_id?: number | null;
  rerank_id?: string;
  tenant_rerank_id?: number | null;
  kb_ids?: string[];
  kb_names?: string[];
  update_time?: number;
};

type KnowledgebaseRow = {
  id: string;
  tenant_id: string;
  tenant_label: string;
  name: string;
  permission: string;
  doc_num: number;
  chunk_num: number;
  token_num: number;
  status: string;
};

type TenantRelationPayload = {
  current_user_id: string;
  users: UserRow[];
  memberships: MembershipRow[];
  dialogs: DialogOwnerRow[];
  knowledgebases: KnowledgebaseRow[];
  asset_counts: Record<string, AssetCounts>;
};

function userDisplayName(user?: Partial<UserRow> | null) {
  return user?.nickname || user?.email || '未命名用户';
}

function userLabelById(users: UserRow[], id: string) {
  return userDisplayName(users.find((user) => user.id === id)) || '未知租户';
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

function inferVoiceProfileConfig(profile: string) {
  const next: Partial<TtsEngineSettings> = {};
  if (profile.startsWith('female_')) {
    next.default_gender = 'female';
  } else if (profile.startsWith('male_')) {
    next.default_gender = 'male';
  }

  if (profile.includes('_cantonese_')) {
    next.default_dialect = 'cantonese';
  } else if (profile.includes('_mandarin_')) {
    next.default_dialect = 'mandarin';
  }
  return next;
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
  const [dialogKbTargets, setDialogKbTargets] = useState<
    Record<string, string[]>
  >({});

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

  useEffect(() => {
    if (!data?.dialogs) return;
    setDialogKbTargets((previous) => {
      const next = { ...previous };
      data.dialogs.forEach((dialog) => {
        if (!next[dialog.id]) {
          next[dialog.id] = dialog.kb_ids ?? [];
        }
      });
      return next;
    });
  }, [data?.dialogs]);

  const users = data?.users ?? [];
  const memberships = (data?.memberships ?? []).filter(
    (item) => item.status === '1',
  );
  const dialogs = data?.dialogs ?? [];
  const knowledgebases = data?.knowledgebases ?? [];
  const tenantIds = Array.from(
    new Set([
      ...memberships.map((item) => item.tenant_id),
      ...dialogs.map((item) => item.tenant_id),
      ...knowledgebases.map((item) => item.tenant_id),
    ]),
  );

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
        `确认把聊天助手「${dialog.name}」迁移到租户「${userLabelById(users, targetTenantId)}」？迁移后只能选择该租户下的知识库。`,
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

  const handleUpdateDialogKbs = async (dialog: DialogOwnerRow) => {
    const kbIds = dialogKbTargets[dialog.id] ?? [];
    const res = await request({
      url: `${tenantRelationsApi}/dialogs/${dialog.id}/knowledgebases`,
      method: 'put',
      data: { kb_ids: kbIds },
    });
    if (res.data?.code === 0) {
      setData(res.data.data);
      message.success('聊天助手知识库已更新');
    } else {
      message.error(res.data?.message || '更新失败');
    }
  };

  const toggleDialogKb = (dialogId: string, kbId: string, checked: boolean) => {
    setDialogKbTargets((previous) => {
      const current = previous[dialogId] ?? [];
      return {
        ...previous,
        [dialogId]: checked
          ? Array.from(new Set([...current, kbId]))
          : current.filter((id) => id !== kbId),
      };
    });
  };

  return (
    <article className="rounded-lg border border-border bg-bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-text-primary">
            租户关系维护
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            这里按租户展示成员、聊天助手和助手可访问知识库。系统里的“租户”本质上是一个用户空间，用户加入某个租户后，就能使用该租户下发布的助手和知识库。
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
              {userDisplayName(user)}
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
              {userDisplayName(user)}
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
          保存用户归属
        </Button>
      </form>

      <section className="mt-6 grid gap-4">
        {tenantIds.map((tenantId) => {
          const tenant = users.find((user) => user.id === tenantId);
          const tenantName = userDisplayName(tenant);
          const tenantMembers = memberships.filter(
            (item) => item.tenant_id === tenantId,
          );
          const tenantDialogs = dialogs.filter(
            (dialog) => dialog.tenant_id === tenantId,
          );
          const tenantKbs = knowledgebases.filter(
            (kb) => kb.tenant_id === tenantId,
          );

          return (
            <article
              key={tenantId}
              className="rounded-lg border border-border/70 bg-bg-base/40 p-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-text-primary">
                    租户：{tenantName}
                  </h3>
                  <p className="mt-1 text-xs text-text-secondary">
                    {formatCounts(data?.asset_counts?.[tenantId] ?? {})}
                  </p>
                </div>
                <span className="rounded-full bg-bg-card px-3 py-1 text-xs text-text-secondary">
                  {tenantMembers.length} 个用户 / {tenantDialogs.length}{' '}
                  个聊天助手 / {tenantKbs.length} 个知识库
                </span>
              </div>

              <div className="mt-4 grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
                <section className="rounded-md bg-bg-card p-3">
                  <h4 className="text-sm font-medium text-text-primary">
                    属于该租户的用户
                  </h4>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {tenantMembers.length === 0 ? (
                      <span className="text-xs text-text-secondary">
                        暂无用户归属到该租户
                      </span>
                    ) : (
                      tenantMembers.map((member) => (
                        <span
                          key={member.id}
                          className="inline-flex items-center gap-2 rounded-full bg-bg-base px-3 py-1 text-xs"
                          title={`${member.user_label} 属于 ${tenantName}`}
                        >
                          <span>{member.user_label}</span>
                          <span className="text-text-secondary">
                            {member.role}
                          </span>
                          <button
                            type="button"
                            className="text-state-error disabled:cursor-not-allowed disabled:opacity-40"
                            disabled={!member.can_delete}
                            title={
                              member.can_delete
                                ? '移除用户归属'
                                : `仍有下级资产：${member.delete_blockers.join(' / ')}`
                            }
                            onClick={() => handleDeleteRelation(member)}
                          >
                            ×
                          </button>
                        </span>
                      ))
                    )}
                  </div>

                  <h4 className="mt-5 text-sm font-medium text-text-primary">
                    该租户的知识库
                  </h4>
                  <div className="mt-3 grid gap-2">
                    {tenantKbs.length === 0 ? (
                      <span className="text-xs text-text-secondary">
                        暂无知识库
                      </span>
                    ) : (
                      tenantKbs.map((kb) => (
                        <div
                          key={kb.id}
                          className="rounded-md border border-border/60 bg-bg-base px-3 py-2 text-xs"
                        >
                          <div className="font-medium text-text-primary">
                            {kb.name}
                          </div>
                          <div className="mt-1 text-text-secondary">
                            {kb.doc_num} 文件 / {kb.chunk_num} 切片 /{' '}
                            {kb.permission}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </section>

                <section className="grid gap-3">
                  {tenantDialogs.length === 0 ? (
                    <div className="rounded-md bg-bg-card p-4 text-sm text-text-secondary">
                      该租户下暂无聊天助手。
                    </div>
                  ) : (
                    tenantDialogs.map((dialog) => {
                      const selectedKbIds =
                        dialogKbTargets[dialog.id] ?? dialog.kb_ids ?? [];
                      return (
                        <div
                          key={dialog.id}
                          className="rounded-md border border-border/70 bg-bg-card p-4"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0">
                              <h4 className="truncate text-sm font-semibold text-text-primary">
                                聊天助手：{dialog.name}
                              </h4>
                              <p className="mt-1 text-xs text-text-secondary">
                                租户「{tenantName}」的成员可以使用该助手。
                              </p>
                              <p className="mt-1 max-w-2xl truncate text-xs text-text-secondary">
                                当前知识库：
                                {dialog.kb_names?.length
                                  ? dialog.kb_names.join('、')
                                  : '未绑定知识库'}
                              </p>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
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
                                <option value="">迁移到其他租户</option>
                                {users.map((user) => (
                                  <option key={user.id} value={user.id}>
                                    {userDisplayName(user)}
                                  </option>
                                ))}
                              </select>
                              <Button
                                size="xs"
                                variant="outline"
                                disabled={
                                  !dialogTargets[dialog.id] ||
                                  dialogTargets[dialog.id] === dialog.tenant_id
                                }
                                onClick={() => handleTransferDialog(dialog)}
                              >
                                保存归属
                              </Button>
                            </div>
                          </div>

                          <div className="mt-4 rounded-md bg-bg-base/60 p-3">
                            <div className="mb-2 text-xs font-medium text-text-primary">
                              可访问知识库
                            </div>
                            {tenantKbs.length === 0 ? (
                              <div className="text-xs text-text-secondary">
                                该租户下暂无可绑定知识库。
                              </div>
                            ) : (
                              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                                {tenantKbs.map((kb) => (
                                  <label
                                    key={kb.id}
                                    className="flex items-start gap-2 rounded-md bg-bg-card px-3 py-2 text-xs"
                                  >
                                    <input
                                      className="mt-0.5"
                                      type="checkbox"
                                      checked={selectedKbIds.includes(kb.id)}
                                      onChange={(event) =>
                                        toggleDialogKb(
                                          dialog.id,
                                          kb.id,
                                          event.target.checked,
                                        )
                                      }
                                    />
                                    <span>
                                      <span className="block font-medium text-text-primary">
                                        {kb.name}
                                      </span>
                                      <span className="text-text-secondary">
                                        {kb.doc_num} 文件 / {kb.chunk_num} 切片
                                      </span>
                                    </span>
                                  </label>
                                ))}
                              </div>
                            )}
                            <div className="mt-3 flex justify-end">
                              <Button
                                size="xs"
                                onClick={() => handleUpdateDialogKbs(dialog)}
                              >
                                保存知识库权限
                              </Button>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                </section>
              </div>
            </article>
          );
        })}
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

function TtsEngineSettingsCard() {
  const [settings, setSettings] = useState<TtsEngineSettings>(
    defaultTtsEngineSettings,
  );
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await request.get(ttsEngineSettingsApi);
      if (res.data?.code === 0) {
        setSettings({
          ...defaultTtsEngineSettings,
          ...res.data.data,
        });
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const updateSetting = <K extends keyof TtsEngineSettings>(
    key: K,
    value: TtsEngineSettings[K],
  ) => {
    setSettings((previous) => ({
      ...previous,
      [key]: value,
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await request.put(ttsEngineSettingsApi, settings);
      if (res.data?.code === 0) {
        setSettings({
          ...defaultTtsEngineSettings,
          ...res.data.data,
        });
        message.success('TTS 引擎配置已保存');
      }
    } finally {
      setSaving(false);
    }
  };

  const handlePreview = async () => {
    if (!settings.tts_enabled) {
      message.warning('请先启用 TTS 语音能力');
      return;
    }
    setPreviewing(true);
    try {
      const res = await request.post(
        '/api/v1/chat/audio/speech',
        {
          text: '欢迎访问时和专业AI顾问。This is a speech preview.',
          tts_config: {
            speed: settings.default_speed,
            emotion: settings.default_emotion,
            dialect: settings.default_dialect,
            gender: settings.default_gender,
            voice_profile: settings.default_voice_profile,
          },
        },
        { responseType: 'blob' },
      );
      const url = window.URL.createObjectURL(res.data);
      const audio = new Audio(url);
      audio.onended = () => window.URL.revokeObjectURL(url);
      await audio.play();
    } catch (error) {
      void error;
      message.error('试听生成失败');
    } finally {
      setPreviewing(false);
    }
  };

  const capabilityItems: Array<[keyof TtsEngineSettings, string]> = [
    ['supports_speed', '语速'],
    ['supports_emotion', '情绪'],
    ['supports_dialect', '方言'],
    ['supports_voice_profile', '音色 Profile'],
    ['supports_sync_caption', '声文同步'],
  ];

  return (
    <article className="rounded-lg border border-border bg-bg-card p-5 md:col-span-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-text-primary">
            TTS 语音引擎
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            只有在这里启用
            TTS，并声明引擎支持对应能力后，聊天助手和智能体才显示语音参数配置。
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          loading={loading}
          onClick={loadSettings}
        >
          刷新
        </Button>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <label className="flex items-center gap-3 rounded-md bg-bg-base/60 p-3 text-sm">
          <input
            type="checkbox"
            checked={settings.tts_enabled}
            onChange={(event) =>
              updateSetting('tts_enabled', event.target.checked)
            }
          />
          <span>
            启用 TTS 语音能力
            <span className="ml-2 text-xs text-text-secondary">
              关闭后不缓存、不排队、不延迟文字输出。
            </span>
          </span>
        </label>

        <label className="grid gap-2 text-sm">
          <span className="text-text-secondary">引擎名称</span>
          <select
            className="h-9 rounded-md bg-bg-input px-3 text-sm outline-none"
            value={settings.engine}
            onChange={(event) => updateSetting('engine', event.target.value)}
          >
            {ttsEngineOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <section className="mt-5">
        <h3 className="mb-3 text-sm font-semibold text-text-primary">
          引擎能力声明
        </h3>
        <div className="grid gap-3 md:grid-cols-5">
          {capabilityItems.map(([key, label]) => (
            <label
              key={key}
              className="flex items-center gap-2 rounded-md bg-bg-base/60 px-3 py-2 text-sm"
            >
              <input
                type="checkbox"
                checked={Boolean(settings[key])}
                onChange={(event) =>
                  updateSetting(key, event.target.checked as never)
                }
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </section>

      <section className="mt-5 grid gap-4 md:grid-cols-3">
        <label className="grid gap-2 text-sm">
          <span className="text-text-secondary">默认语速</span>
          <select
            className="h-9 rounded-md bg-bg-input px-3 text-sm outline-none"
            value={settings.default_speed}
            onChange={(event) =>
              updateSetting('default_speed', Number(event.target.value))
            }
            disabled={!settings.supports_speed}
          >
            {!ttsSpeedOptions.some(
              ([value]) => Number(value) === Number(settings.default_speed),
            ) && (
              <option value={settings.default_speed}>
                当前 {settings.default_speed}x
              </option>
            )}
            {ttsSpeedOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="grid gap-2 text-sm">
          <span className="text-text-secondary">默认情绪</span>
          <select
            className="h-9 rounded-md bg-bg-input px-3 text-sm outline-none"
            value={settings.default_emotion}
            onChange={(event) =>
              updateSetting('default_emotion', event.target.value)
            }
            disabled={!settings.supports_emotion}
          >
            {ttsEmotionOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="grid gap-2 text-sm">
          <span className="text-text-secondary">默认中文方言</span>
          <select
            className="h-9 rounded-md bg-bg-input px-3 text-sm outline-none"
            value={settings.default_dialect}
            onChange={(event) =>
              updateSetting('default_dialect', event.target.value)
            }
            disabled={!settings.supports_dialect}
          >
            {ttsDialectOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="grid gap-2 text-sm">
          <span className="text-text-secondary">默认性别</span>
          <select
            className="h-9 rounded-md bg-bg-input px-3 text-sm outline-none"
            value={settings.default_gender}
            onChange={(event) =>
              updateSetting('default_gender', event.target.value)
            }
          >
            <option value="female">女声</option>
            <option value="male">男声</option>
          </select>
        </label>

        <label className="grid gap-2 text-sm">
          <span className="text-text-secondary">默认音色 Profile</span>
          <select
            className="h-9 rounded-md bg-bg-input px-3 text-sm outline-none"
            value={settings.default_voice_profile}
            onChange={(event) => {
              const profile = event.target.value;
              setSettings((previous) => ({
                ...previous,
                default_voice_profile: profile,
                ...inferVoiceProfileConfig(profile),
              }));
            }}
            disabled={!settings.supports_voice_profile}
          >
            {!ttsVoiceProfileOptions.some(
              ([value]) => value === settings.default_voice_profile,
            ) && (
              <option value={settings.default_voice_profile}>
                当前：{settings.default_voice_profile}
              </option>
            )}
            {ttsVoiceProfileOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        <label className="grid gap-2 text-sm">
          <span className="text-text-secondary">首段缓冲 ms</span>
          <Input
            type="number"
            min="300"
            max="5000"
            step="100"
            value={settings.buffer_ms}
            onChange={(event) =>
              updateSetting('buffer_ms', Number(event.target.value))
            }
            disabled={!settings.supports_sync_caption}
          />
        </label>

        <label className="grid gap-2 text-sm">
          <span className="text-text-secondary">中文分段字数</span>
          <Input
            type="number"
            min="10"
            max="120"
            value={settings.segment_max_chars_zh}
            onChange={(event) =>
              updateSetting('segment_max_chars_zh', Number(event.target.value))
            }
          />
        </label>

        <label className="grid gap-2 text-sm">
          <span className="text-text-secondary">英文分段词数</span>
          <Input
            type="number"
            min="5"
            max="60"
            value={settings.segment_max_words_en}
            onChange={(event) =>
              updateSetting('segment_max_words_en', Number(event.target.value))
            }
          />
        </label>
      </section>

      <div className="mt-5 flex justify-end gap-3">
        <ButtonLoading
          type="button"
          loading={previewing}
          onClick={handlePreview}
          disabled={!settings.tts_enabled}
          variant="outline"
        >
          试听
        </ButtonLoading>
        <ButtonLoading
          type="button"
          loading={saving}
          onClick={handleSave}
          className="bg-[#6f3f2f] text-white dark:bg-[#2d5f80]"
        >
          保存 TTS 配置
        </ButtonLoading>
      </div>
    </article>
  );
}

function DevEntryCard({ entry }: { entry: (typeof devEntries)[number] }) {
  const { t } = useTranslation();

  return (
    <article className="flex h-44 flex-col rounded-lg border border-border bg-bg-card p-5">
      <h2 className="text-lg font-medium text-text-primary">
        {t(entry.titleKey)}
      </h2>
      <p className="mt-2 line-clamp-3 text-sm leading-5 text-text-secondary">
        {t(entry.descriptionKey)}
      </p>
      <Button asChild className="mt-auto w-24 bg-[#6f3f2f] text-white">
        <Link to={entry.path}>打开</Link>
      </Button>
    </article>
  );
}

export default function DevSettingPanython() {
  useEffect(() => {
    window.sessionStorage.setItem(DEV_FEATURE_SESSION_KEY, '1');
  }, []);

  return (
    <section className="h-full min-h-0 overflow-y-auto px-4 py-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8">
          <h1 className="text-2xl font-semibold text-text-primary">
            Panython 开发管理
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            这些功能用于后台配置，不在普通用户工作台展示。
          </p>
        </header>

        <Tabs defaultValue="menus" className="w-full">
          <TabsList className="mb-4 grid w-full grid-cols-4 lg:w-[640px]">
            <TabsTrigger value="menus">功能入口</TabsTrigger>
            <TabsTrigger value="tts">TTS 语音</TabsTrigger>
            <TabsTrigger value="users">用户注册</TabsTrigger>
            <TabsTrigger value="tenants">租户关系</TabsTrigger>
          </TabsList>

          <TabsContent value="menus">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              {devEntries.map((entry) => (
                <DevEntryCard key={entry.path} entry={entry} />
              ))}
            </div>
          </TabsContent>

          <TabsContent value="tts">
            <TtsEngineSettingsCard />
          </TabsContent>

          <TabsContent value="users">
            <div className="max-w-xl">
              <RegisterUserCard />
            </div>
          </TabsContent>

          <TabsContent value="tenants">
            <TenantRelationsCard />
          </TabsContent>
        </Tabs>
      </div>
    </section>
  );
}
