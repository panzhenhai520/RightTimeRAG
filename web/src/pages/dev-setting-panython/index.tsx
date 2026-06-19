import { Button, ButtonLoading } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import message from '@/components/ui/message';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useRegister } from '@/hooks/use-login-request';
import { DEV_FEATURE_SESSION_KEY, Routes } from '@/routes';
import { rsaPsw } from '@/utils';
import request from '@/utils/next-request';
import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
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
    titleKey: 'devSettingPanython.createAgent',
    descriptionKey: 'devSettingPanython.createAgentDescription',
    path: Routes.AgentTemplates,
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
const tenantRelationLogsApi = '/api/v1/dev/tenant-relations/logs';
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
  ['professional', 'devSettingPanython.ttsEmotionProfessional'],
  ['calm', 'devSettingPanython.ttsEmotionCalm'],
  ['friendly', 'devSettingPanython.ttsEmotionFriendly'],
  ['formal', 'devSettingPanython.ttsEmotionFormal'],
  ['lively', 'devSettingPanython.ttsEmotionLively'],
  ['serious', 'devSettingPanython.ttsEmotionSerious'],
];

const ttsDialectOptions = [
  ['mandarin', 'devSettingPanython.ttsDialectMandarin'],
  ['cantonese', 'devSettingPanython.ttsDialectCantonese'],
  ['sichuan', 'devSettingPanython.ttsDialectSichuan'],
  ['shanghai', 'devSettingPanython.ttsDialectShanghai'],
  ['dongbei', 'devSettingPanython.ttsDialectDongbei'],
  ['minnan', 'devSettingPanython.ttsDialectMinnan'],
  ['tianjin', 'devSettingPanython.ttsDialectTianjin'],
  ['shandong', 'devSettingPanython.ttsDialectShandong'],
];

const ttsVoiceProfileOptions = [
  ['female_mandarin_01', 'devSettingPanython.ttsVoiceFemaleMandarin'],
  ['male_mandarin_01', 'devSettingPanython.ttsVoiceMaleMandarin'],
  ['female_cantonese_01', 'devSettingPanython.ttsVoiceFemaleCantonese'],
  ['male_cantonese_01', 'devSettingPanython.ttsVoiceMaleCantonese'],
  ['female_english_01', 'devSettingPanython.ttsVoiceFemaleEnglish'],
  ['male_english_01', 'devSettingPanython.ttsVoiceMaleEnglish'],
];

const ttsEngineOptions = [
  ['CosyVoice3', 'CosyVoice 3'],
  ['CosyVoice2', 'CosyVoice 2'],
];

const ttsSpeedOptions = [
  [0.8, 'devSettingPanython.ttsSpeedSlow'],
  [1, 'devSettingPanython.ttsSpeedNormal'],
  [1.15, 'devSettingPanython.ttsSpeedSlightlyFast'],
  [1.3, 'devSettingPanython.ttsSpeedFast'],
];

const ttsBooleanOptions = [
  ['true', 'devSettingPanython.optionEnabled'],
  ['false', 'devSettingPanython.optionDisabled'],
];

const ttsBufferOptions = [800, 1200, 1600, 2000, 3000];
const ttsZhSegmentOptions = [30, 45, 60, 80, 100];
const ttsEnSegmentOptions = [12, 18, 24, 36, 48];

const ttsFieldRowClass =
  'grid grid-cols-[max-content_minmax(170px,250px)] items-center justify-start gap-2 text-sm';
const ttsFieldLabelClass =
  'inline-flex items-center gap-1 whitespace-nowrap text-text-secondary';
const ttsSelectClass =
  'h-9 w-full border-0 border-b border-border-button bg-transparent px-0 pr-8 text-sm text-text-primary outline-none disabled:cursor-not-allowed disabled:opacity-50';

const userGroupFieldRowClass =
  'grid grid-cols-[max-content_minmax(180px,260px)] items-center justify-start gap-2 text-sm';
const userGroupSelectClass =
  'h-9 w-full border-0 border-b border-border-button bg-transparent px-0 pr-8 text-sm text-text-primary outline-none';

const userGroupRoleOptions = [
  ['normal', 'devSettingPanython.roleNormal'],
  ['admin', 'devSettingPanython.roleAdmin'],
  ['owner', 'devSettingPanython.roleOwner'],
];

function TtsHelpButton({ text }: { text: string }) {
  return (
    <button
      type="button"
      className="inline-flex size-4 items-center justify-center rounded-full border border-border-button text-[10px] font-semibold leading-none text-text-secondary transition hover:border-[#6f3f2f] hover:text-[#6f3f2f] dark:hover:border-[#9bc7dd] dark:hover:text-[#9bc7dd]"
      title={text}
      aria-label={text}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        message.info(text);
      }}
    >
      ?
    </button>
  );
}

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

type OperationLogRow = {
  id: string;
  operator_id: string;
  operator_label?: string;
  action: string;
  target_type: string;
  target_id?: string;
  target_label?: string;
  tenant_id?: string;
  details?: Record<string, unknown>;
  create_time?: number;
  create_date?: string;
};

function userDisplayName(
  user: Partial<UserRow> | null | undefined,
  fallback: string,
) {
  return user?.nickname || user?.email || fallback;
}

function userLabelById(users: UserRow[], id: string, fallback: string) {
  return userDisplayName(
    users.find((user) => user.id === id),
    fallback,
  );
}

function formatCounts(
  counts: AssetCounts = {},
  t: ReturnType<typeof useTranslation>['t'],
) {
  const labels: Record<string, string> = {
    members: t('devSettingPanython.assetMembers'),
    datasets: t('devSettingPanython.assetDatasets'),
    dialogs: t('devSettingPanython.assetDialogs'),
    searches: t('devSettingPanython.assetSearches'),
    agents: t('devSettingPanython.assetAgents'),
    memories: t('devSettingPanython.assetMemories'),
    models: t('devSettingPanython.assetModels'),
  };
  return (
    Object.entries(counts)
      .filter(([, value]) => value > 0)
      .map(([key, value]) => `${labels[key] ?? key}:${value}`)
      .join(' / ') || t('devSettingPanython.noDependentAssets')
  );
}

function roleLabel(role: string, t: ReturnType<typeof useTranslation>['t']) {
  const matched = userGroupRoleOptions.find(([value]) => value === role);
  return matched ? t(matched[1]) : role;
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
  const { t } = useTranslation();
  const [data, setData] = useState<TenantRelationPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [userId, setUserId] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [role, setRole] = useState('normal');
  const [selectedTenantId, setSelectedTenantId] = useState('');
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
  const kbById = new Map(knowledgebases.map((kb) => [kb.id, kb]));
  const tenantIds = Array.from(
    new Set([
      ...memberships.map((item) => item.tenant_id),
      ...dialogs.map((item) => item.tenant_id),
      ...knowledgebases.map((item) => item.tenant_id),
    ]),
  );
  const defaultTenantId = useMemo(() => {
    const adminTenantId = tenantIds.find((tenantId) => {
      const tenant = users.find((user) => user.id === tenantId);
      return userDisplayName(tenant, '').trim().toLowerCase() === 'admin';
    });
    return adminTenantId ?? tenantIds[0] ?? '';
  }, [tenantIds, users]);
  const activeTenantId =
    selectedTenantId && tenantIds.includes(selectedTenantId)
      ? selectedTenantId
      : defaultTenantId;

  useEffect(() => {
    if (!selectedTenantId && defaultTenantId) {
      setSelectedTenantId(defaultTenantId);
    }
  }, [defaultTenantId, selectedTenantId]);

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
      message.success(t('devSettingPanython.tenantRelationSaved'));
    }
  };

  const handleDeleteRelation = async (relation: MembershipRow) => {
    const blockers = relation.delete_blockers || [];
    if (blockers.length > 0) {
      window.alert(
        t('devSettingPanython.deleteRelationBlocked', {
          blockers: blockers.join(' / '),
        }),
      );
      return;
    }
    if (
      !window.confirm(
        t('devSettingPanython.deleteRelationConfirm', {
          user: relation.user_label,
          tenant: relation.tenant_label,
        }),
      )
    ) {
      return;
    }
    const res = await request.delete(`${tenantRelationsApi}/${relation.id}`);
    if (res.data?.code === 0) {
      setData(res.data.data);
      message.success(t('devSettingPanython.tenantRelationDeleted'));
    }
  };

  const handleDeleteUserGroup = async (
    relation: MembershipRow | undefined,
    tenantName: string,
  ) => {
    if (!relation) {
      message.warning(t('devSettingPanython.noGroupOwnerRelation'));
      return;
    }
    const blockers = relation.delete_blockers || [];
    if (blockers.length > 0) {
      window.alert(
        t('devSettingPanython.deleteGroupBlocked', {
          blockers: blockers.join(' / '),
        }),
      );
      return;
    }
    if (
      !window.confirm(
        t('devSettingPanython.deleteGroupConfirm', {
          tenant: tenantName,
        }),
      )
    ) {
      return;
    }
    const res = await request.delete(`${tenantRelationsApi}/${relation.id}`);
    if (res.data?.code === 0) {
      setData(res.data.data);
      message.success(t('devSettingPanython.userGroupDeleted'));
    } else {
      message.error(res.data?.message || t('devSettingPanython.updateFailed'));
    }
  };

  const handleTransferDialog = async (dialog: DialogOwnerRow) => {
    const targetTenantId = dialogTargets[dialog.id];
    if (!targetTenantId || targetTenantId === dialog.tenant_id) return;
    if (
      !window.confirm(
        t('devSettingPanython.transferDialogConfirm', {
          dialog: dialog.name,
          tenant: userLabelById(
            users,
            targetTenantId,
            t('devSettingPanython.unknownTenant'),
          ),
        }),
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
      message.success(t('devSettingPanython.dialogTenantSaved'));
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
      message.success(t('devSettingPanython.dialogKnowledgeSaved'));
    } else {
      message.error(res.data?.message || t('devSettingPanython.updateFailed'));
    }
  };

  const handleDeleteDialog = async (dialog: DialogOwnerRow) => {
    if (
      !window.confirm(
        t('devSettingPanython.deleteDialogConfirm', {
          dialog: dialog.name,
        }),
      )
    ) {
      return;
    }
    const res = await request.delete(
      `${tenantRelationsApi}/dialogs/${dialog.id}`,
    );
    if (res.data?.code === 0) {
      setData(res.data.data);
      message.success(t('devSettingPanython.dialogDeleted'));
    } else {
      message.error(res.data?.message || t('devSettingPanython.updateFailed'));
    }
  };

  const handleDeleteUser = async (user: UserRow) => {
    if (
      !window.confirm(
        t('devSettingPanython.deleteUserConfirm', {
          user: userDisplayName(user, t('devSettingPanython.unnamedUser')),
        }),
      )
    ) {
      return;
    }
    const res = await request.delete(`/api/v1/dev/users/${user.id}`);
    if (res.data?.code === 0) {
      setData(res.data.data);
      message.success(t('devSettingPanython.userDeleted'));
    } else {
      const blockers = res.data?.data?.blockers;
      if (Array.isArray(blockers) && blockers.length > 0) {
        window.alert(
          t('devSettingPanython.deleteUserBlocked', {
            blockers: blockers.join(' / '),
          }),
        );
      } else {
        message.error(
          res.data?.message || t('devSettingPanython.updateFailed'),
        );
      }
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
            {t('devSettingPanython.tenantRelationsTitle')}
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            {t('devSettingPanython.tenantRelationsDescription')}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          loading={loading}
          onClick={loadRelations}
        >
          {t('devSettingPanython.refresh')}
        </Button>
      </div>

      <details className="mt-5 rounded-lg border border-border/70 bg-bg-base/40 p-4">
        <summary className="cursor-pointer text-base font-semibold text-text-primary">
          {t('devSettingPanython.userGroupMaintenanceTitle')}
        </summary>
        <form
          className="mt-4 grid gap-x-8 gap-y-3 rounded-md bg-bg-base/60 p-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]"
          onSubmit={handleUpsertRelation}
        >
          <label className={userGroupFieldRowClass}>
            <span className="truncate text-text-secondary">
              {t('devSettingPanython.selectUserGroup')}:
            </span>
            <select
              className={userGroupSelectClass}
              value={tenantId}
              onChange={(event) => setTenantId(event.target.value)}
            >
              <option value="">
                {t('devSettingPanython.selectUserGroup')}
              </option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {userDisplayName(user, t('devSettingPanython.unnamedUser'))}
                </option>
              ))}
            </select>
          </label>
          <label className={userGroupFieldRowClass}>
            <span className="truncate text-text-secondary">
              {t('devSettingPanython.selectUser')}:
            </span>
            <select
              className={userGroupSelectClass}
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
            >
              <option value="">{t('devSettingPanython.selectUser')}</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {userDisplayName(user, t('devSettingPanython.unnamedUser'))}
                </option>
              ))}
            </select>
          </label>
          <label className={userGroupFieldRowClass}>
            <span className="truncate text-text-secondary">
              {t('devSettingPanython.knowledgeRole')}:
            </span>
            <select
              className={userGroupSelectClass}
              value={role}
              onChange={(event) => setRole(event.target.value)}
            >
              {userGroupRoleOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {t(label)}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-center lg:justify-end">
            <Button type="submit" disabled={!userId || !tenantId}>
              {t('devSettingPanython.saveUserGroupMembership')}
            </Button>
          </div>
        </form>

        <div className="mt-3 grid gap-2 rounded-md border border-border/60 bg-bg-base/40 p-3 text-xs text-text-secondary md:grid-cols-3">
          <div>
            <span className="font-medium text-text-primary">
              {t('devSettingPanython.roleNormal')}:
            </span>{' '}
            {t('devSettingPanython.roleNormalDescription')}
          </div>
          <div>
            <span className="font-medium text-text-primary">
              {t('devSettingPanython.roleAdmin')}:
            </span>{' '}
            {t('devSettingPanython.roleAdminDescription')}
          </div>
          <div>
            <span className="font-medium text-text-primary">
              {t('devSettingPanython.roleOwner')}:
            </span>{' '}
            {t('devSettingPanython.roleOwnerDescription')}
          </div>
        </div>
      </details>

      <details className="mt-6 rounded-lg border border-border/70 bg-bg-base/40 p-4">
        <summary className="cursor-pointer text-base font-semibold text-text-primary">
          {t('devSettingPanython.userAccountsTitle')}
        </summary>
        <p className="mt-1 text-xs text-text-secondary">
          {t('devSettingPanython.userAccountsDescription')}
        </p>
        <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {users.map((user) => (
            <div
              key={user.id}
              className="flex items-center justify-between gap-3 rounded-md bg-bg-card px-3 py-2 text-xs"
            >
              <span className="min-w-0">
                <span className="block truncate font-medium text-text-primary">
                  {userDisplayName(user, t('devSettingPanython.unnamedUser'))}
                </span>
                <span className="text-text-secondary">
                  {user.is_superuser
                    ? t('devSettingPanython.superuser')
                    : t('devSettingPanython.regularUser')}
                </span>
              </span>
              <Button
                type="button"
                size="xs"
                variant="outline"
                className="border-state-error text-state-error"
                disabled={user.id === data?.current_user_id}
                onClick={() => handleDeleteUser(user)}
              >
                {t('devSettingPanython.deleteUser')}
              </Button>
            </div>
          ))}
        </div>
      </details>

      <section className="mt-6 grid items-start gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="rounded-lg border border-border/70 bg-bg-base/40 p-3">
          <h3 className="text-base font-semibold text-text-primary">
            {t('devSettingPanython.userGroupTreeTitle')}
          </h3>
          <p className="mt-1 text-xs text-text-secondary">
            {t('devSettingPanython.userGroupTreeDescription')}
          </p>
          <div className="mt-4 flex flex-col gap-2 pr-1">
            {tenantIds.map((tenantId) => {
              const tenant = users.find((user) => user.id === tenantId);
              const tenantName = userDisplayName(
                tenant,
                t('devSettingPanython.unnamedTenant'),
              );
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
                <button
                  key={tenantId}
                  type="button"
                  className={`rounded-md border p-3 text-left text-xs transition ${
                    tenantId === activeTenantId
                      ? 'border-[#6f3f2f] bg-[#6f3f2f]/10 text-[#6f3f2f] dark:border-[#9bc7dd] dark:bg-[#2d5f80]/25 dark:text-[#9bc7dd]'
                      : 'border-border/60 bg-bg-card text-text-primary hover:border-[#6f3f2f]/50 dark:hover:border-[#9bc7dd]/60'
                  }`}
                  onClick={() => setSelectedTenantId(tenantId)}
                >
                  <div className="truncate font-semibold">
                    {t('devSettingPanython.userGroupLabel', {
                      group: tenantName,
                    })}
                  </div>
                  <div className="mt-2 text-text-secondary">
                    {t('devSettingPanython.tenantSummary', {
                      users: tenantMembers.length,
                      dialogs: tenantDialogs.length,
                      kbs: tenantKbs.length,
                    })}
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="grid min-w-0 gap-4">
          {(activeTenantId ? [activeTenantId] : []).map((tenantId) => {
            const tenant = users.find((user) => user.id === tenantId);
            const tenantName = userDisplayName(
              tenant,
              t('devSettingPanython.unnamedTenant'),
            );
            const tenantMembers = memberships.filter(
              (item) => item.tenant_id === tenantId,
            );
            const tenantDialogs = dialogs.filter(
              (dialog) => dialog.tenant_id === tenantId,
            );
            const tenantKbs = knowledgebases.filter((kb) => {
              return kb.tenant_id === tenantId;
            });
            const ownerRelation = tenantMembers.find(
              (item) => item.user_id === tenantId || item.role === 'owner',
            );

            return (
              <article
                key={tenantId}
                className="rounded-lg border border-border/70 bg-bg-base/40 p-4"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold text-text-primary">
                      {t('devSettingPanython.userGroupLabel', {
                        group: tenantName,
                      })}
                    </h3>
                    <p className="mt-1 text-xs text-text-secondary">
                      {formatCounts(data?.asset_counts?.[tenantId] ?? {}, t)}
                    </p>
                  </div>
                  <span className="rounded-full bg-bg-card px-3 py-1 text-xs text-text-secondary">
                    {t('devSettingPanython.tenantSummary', {
                      users: tenantMembers.length,
                      dialogs: tenantDialogs.length,
                      kbs: tenantKbs.length,
                    })}
                  </span>
                  <Button
                    type="button"
                    size="xs"
                    variant="outline"
                    className="border-state-error text-state-error"
                    onClick={() =>
                      handleDeleteUserGroup(ownerRelation, tenantName)
                    }
                  >
                    {t('devSettingPanython.deleteUserGroup')}
                  </Button>
                </div>

                <div className="mt-4 grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
                  <section className="rounded-md bg-bg-card p-3">
                    <h4 className="text-sm font-medium text-text-primary">
                      {t('devSettingPanython.groupMembers')}
                    </h4>
                    <div className="mt-3 space-y-2">
                      {tenantMembers.length === 0 ? (
                        <span className="text-xs text-text-secondary">
                          {t('devSettingPanython.noTenantUsers')}
                        </span>
                      ) : (
                        tenantMembers.map((member) => (
                          <div
                            key={member.id}
                            className="flex items-center justify-between gap-2 rounded-md bg-bg-base px-3 py-2 text-xs"
                            title={t('devSettingPanython.userBelongsToTenant', {
                              user: member.user_label,
                              tenant: tenantName,
                            })}
                          >
                            <span className="min-w-0">
                              <span className="block truncate text-text-primary">
                                {member.user_label}
                              </span>
                              <span className="text-text-secondary">
                                {roleLabel(member.role, t)}
                              </span>
                            </span>
                            <button
                              type="button"
                              className="text-state-error disabled:cursor-not-allowed disabled:opacity-40"
                              disabled={!member.can_delete}
                              title={
                                member.can_delete
                                  ? t('devSettingPanython.removeUserTenant')
                                  : t('devSettingPanython.hasDependentAssets', {
                                      blockers:
                                        member.delete_blockers.join(' / '),
                                    })
                              }
                              onClick={() => handleDeleteRelation(member)}
                            >
                              ×
                            </button>
                          </div>
                        ))
                      )}
                    </div>

                    <h4 className="mt-5 text-sm font-medium text-text-primary">
                      {t('devSettingPanython.groupKnowledgebases')}
                    </h4>
                    <div className="mt-3 grid gap-2">
                      {tenantKbs.length === 0 ? (
                        <span className="text-xs text-text-secondary">
                          {t('devSettingPanython.noKnowledgebases')}
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
                              {t('devSettingPanython.kbStats', {
                                docs: kb.doc_num,
                                chunks: kb.chunk_num,
                                permission: kb.permission,
                              })}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </section>

                  <section className="relative grid gap-3 border-l border-border/70 pl-4">
                    <span className="absolute -left-[5px] top-2 h-2.5 w-2.5 rounded-full bg-[#6f3f2f] dark:bg-[#9bc7dd]" />
                    <h4 className="text-sm font-medium text-text-primary">
                      {t('devSettingPanython.groupAssistants')}
                    </h4>
                    {tenantDialogs.length === 0 ? (
                      <div className="rounded-md bg-bg-card p-4 text-sm text-text-secondary">
                        {t('devSettingPanython.noDialogsInTenant')}
                      </div>
                    ) : (
                      tenantDialogs.map((dialog) => {
                        const selectedKbIds =
                          dialogKbTargets[dialog.id] ?? dialog.kb_ids ?? [];
                        const selectedKbs = selectedKbIds
                          .map((kbId) => kbById.get(kbId))
                          .filter(Boolean) as KnowledgebaseRow[];
                        return (
                          <div
                            key={dialog.id}
                            className="relative rounded-md border border-border/70 bg-bg-card p-3"
                          >
                            <span className="absolute -left-[21px] top-5 h-px w-4 bg-border/70" />
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <div className="min-w-0">
                                <h4 className="truncate text-sm font-semibold text-text-primary">
                                  {t('devSettingPanython.dialogLabel', {
                                    dialog: dialog.name,
                                  })}
                                </h4>
                                <p className="mt-0.5 text-xs text-text-secondary">
                                  {t('devSettingPanython.dialogTenantAccess', {
                                    tenant: tenantName,
                                  })}
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
                                  <option value="">
                                    {t('devSettingPanython.moveToTenant')}
                                  </option>
                                  {users.map((user) => (
                                    <option key={user.id} value={user.id}>
                                      {userDisplayName(
                                        user,
                                        t('devSettingPanython.unnamedUser'),
                                      )}
                                    </option>
                                  ))}
                                </select>
                                <Button
                                  size="xs"
                                  variant="outline"
                                  disabled={
                                    !dialogTargets[dialog.id] ||
                                    dialogTargets[dialog.id] ===
                                      dialog.tenant_id
                                  }
                                  onClick={() => handleTransferDialog(dialog)}
                                >
                                  {t('devSettingPanython.saveOwner')}
                                </Button>
                                <Button
                                  size="xs"
                                  variant="outline"
                                  className="border-state-error text-state-error"
                                  onClick={() => handleDeleteDialog(dialog)}
                                >
                                  {t('devSettingPanython.deleteDialog')}
                                </Button>
                              </div>
                            </div>

                            <div className="mt-3 rounded-md bg-bg-base/50 p-2.5">
                              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
                                <span className="font-medium text-text-primary">
                                  {t(
                                    'devSettingPanython.accessibleKnowledgebases',
                                  )}
                                </span>
                                <span className="text-text-secondary">
                                  {t('devSettingPanython.selectedKbCount', {
                                    count: selectedKbs.length,
                                  })}
                                </span>
                              </div>
                              {selectedKbs.length > 0 && (
                                <div className="mb-2 flex flex-wrap gap-1.5">
                                  {selectedKbs.map((kb) => (
                                    <span
                                      key={kb.id}
                                      className="rounded-full bg-[#6f3f2f]/10 px-2 py-1 text-xs text-[#6f3f2f] dark:bg-[#2d5f80]/25 dark:text-[#9bc7dd]"
                                      title={t(
                                        'devSettingPanython.kbTenantTooltip',
                                        {
                                          kb: kb.name,
                                          tenant: kb.tenant_label,
                                        },
                                      )}
                                    >
                                      {kb.name}
                                    </span>
                                  ))}
                                </div>
                              )}
                              {knowledgebases.length === 0 ? (
                                <div className="text-xs text-text-secondary">
                                  {t(
                                    'devSettingPanython.noBindableKnowledgebases',
                                  )}
                                </div>
                              ) : (
                                <div className="grid gap-1.5 md:grid-cols-2 xl:grid-cols-4">
                                  {knowledgebases.map((kb) => (
                                    <label
                                      key={kb.id}
                                      className="flex cursor-pointer items-start gap-2 rounded-md bg-bg-card px-2.5 py-2 text-xs hover:bg-bg-base"
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
                                          {t(
                                            'devSettingPanython.kbOptionMeta',
                                            {
                                              tenant: kb.tenant_label,
                                              docs: kb.doc_num,
                                              chunks: kb.chunk_num,
                                            },
                                          )}
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
                                  {t('devSettingPanython.saveKnowledgeAccess')}
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
      </section>
    </article>
  );
}

function OperationLogsCard() {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<OperationLogRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await request.get(tenantRelationLogsApi, {
        params: { page: 1, page_size: 80 },
      });
      if (res.data?.code === 0) {
        setLogs(res.data.data?.logs ?? []);
        setTotal(res.data.data?.total ?? 0);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  return (
    <article className="rounded-lg border border-border bg-bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-text-primary">
            {t('devSettingPanython.operationLogsTitle')}
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            {t('devSettingPanython.operationLogsDescription', { total })}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          loading={loading}
          onClick={loadLogs}
        >
          {t('devSettingPanython.refresh')}
        </Button>
      </div>

      <div className="mt-5 overflow-hidden rounded-md border border-border/70">
        <div className="grid grid-cols-[160px_160px_1fr_180px] bg-bg-base px-3 py-2 text-xs font-medium text-text-secondary">
          <span>{t('devSettingPanython.logOperator')}</span>
          <span>{t('devSettingPanython.logAction')}</span>
          <span>{t('devSettingPanython.logTarget')}</span>
          <span>{t('devSettingPanython.logTime')}</span>
        </div>
        {logs.length === 0 ? (
          <div className="px-3 py-6 text-center text-sm text-text-secondary">
            {t('devSettingPanython.noOperationLogs')}
          </div>
        ) : (
          logs.map((log) => (
            <details
              key={log.id}
              className="border-t border-border/60 px-3 py-2 text-xs"
            >
              <summary className="grid cursor-pointer grid-cols-[160px_160px_1fr_180px] items-center gap-2 text-text-primary">
                <span className="truncate">
                  {log.operator_label || log.operator_id}
                </span>
                <span className="truncate">
                  {t(`devSettingPanython.operation_${log.action}`, {
                    defaultValue: log.action,
                  })}
                </span>
                <span className="truncate">
                  {log.target_label || log.target_id || log.target_type}
                </span>
                <span className="truncate">
                  {log.create_date || log.create_time || '-'}
                </span>
              </summary>
              <pre className="mt-2 max-h-48 overflow-auto rounded bg-bg-base p-3 text-[11px] leading-5 text-text-secondary">
                {JSON.stringify(log.details ?? {}, null, 2)}
              </pre>
            </details>
          ))
        )}
      </div>
    </article>
  );
}

function RegisterUserCard() {
  const { t } = useTranslation();
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
      <h2 className="text-lg font-medium text-text-primary">
        {t('devSettingPanython.registerUser')}
      </h2>
      <p className="mt-2 min-h-10 text-sm text-text-secondary">
        {t('devSettingPanython.registerUserDescription')}
      </p>
      <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
        <Input
          value={nickname}
          onChange={(event) => setNickname(event.target.value)}
          placeholder={t('devSettingPanython.userName')}
          autoComplete="username"
        />
        <Input
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder={t('devSettingPanython.email')}
          autoComplete="email"
        />
        <Input
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder={t('devSettingPanython.password')}
          type="password"
          autoComplete="new-password"
        />
        <ButtonLoading
          type="submit"
          loading={loading}
          disabled={disabled}
          className="mt-2 bg-[#6f3f2f] text-white dark:bg-[#2d5f80]"
        >
          {t('devSettingPanython.registerUser')}
        </ButtonLoading>
      </form>
    </article>
  );
}

function TtsEngineSettingsCard() {
  const { t } = useTranslation();
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
        message.success(t('devSettingPanython.ttsSaved'));
      }
    } finally {
      setSaving(false);
    }
  };

  const handlePreview = async () => {
    if (!settings.tts_enabled) {
      message.warning(t('devSettingPanython.enableTtsFirst'));
      return;
    }
    setPreviewing(true);
    try {
      const res = await request.post(
        '/api/v1/chat/audio/speech',
        {
          text: t('devSettingPanython.ttsPreviewText'),
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
      message.error(t('devSettingPanython.previewFailed'));
    } finally {
      setPreviewing(false);
    }
  };

  const capabilityItems: Array<[keyof TtsEngineSettings, string]> = [
    ['supports_emotion', 'devSettingPanython.ttsCapabilityEmotion'],
    ['supports_voice_profile', 'devSettingPanython.ttsCapabilityVoice'],
    ['supports_sync_caption', 'devSettingPanython.ttsCapabilitySync'],
  ];

  return (
    <article className="rounded-lg border border-border bg-bg-card p-5 md:col-span-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-text-primary">
            {t('devSettingPanython.ttsEngineTitle')}
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            {t('devSettingPanython.ttsEngineDescription')}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          loading={loading}
          onClick={loadSettings}
        >
          {t('devSettingPanython.refresh')}
        </Button>
      </div>

      <div className="mt-5 grid gap-x-8 gap-y-3 md:grid-cols-2">
        <label className={ttsFieldRowClass}>
          <span className={ttsFieldLabelClass}>
            {t('devSettingPanython.enableTts')}:
          </span>
          <select
            className={ttsSelectClass}
            value={String(settings.tts_enabled)}
            onChange={(event) =>
              updateSetting('tts_enabled', event.target.value === 'true')
            }
          >
            {ttsBooleanOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {t(label)}
              </option>
            ))}
          </select>
        </label>

        <label className={ttsFieldRowClass}>
          <span className={ttsFieldLabelClass}>
            {t('devSettingPanython.engineName')}:
          </span>
          <select
            className={ttsSelectClass}
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
      <p className="mt-2 text-xs text-text-secondary">
        {t('devSettingPanython.enableTtsDescription')}
      </p>

      <section className="mt-5">
        <h3 className="mb-3 text-sm font-semibold text-text-primary">
          {t('devSettingPanython.engineCapabilities')}
        </h3>
        <div className="grid gap-x-8 gap-y-3 md:grid-cols-2">
          <label className={ttsFieldRowClass}>
            <span className={ttsFieldLabelClass}>
              {t('devSettingPanython.ttsCapabilitySpeed')}:
            </span>
            <select
              className={ttsSelectClass}
              value={String(Boolean(settings.supports_speed))}
              onChange={(event) =>
                updateSetting('supports_speed', event.target.value === 'true')
              }
            >
              {ttsBooleanOptions.map(([value, optionLabel]) => (
                <option key={value} value={value}>
                  {t(optionLabel)}
                </option>
              ))}
            </select>
          </label>

          <label className={ttsFieldRowClass}>
            <span className={ttsFieldLabelClass}>
              {t('devSettingPanython.defaultSpeed')}:
            </span>
            <select
              className={ttsSelectClass}
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
                  {t('devSettingPanython.currentSpeed', {
                    speed: settings.default_speed,
                  })}
                </option>
              )}
              {ttsSpeedOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {t(String(label))}
                </option>
              ))}
            </select>
          </label>

          <label className={ttsFieldRowClass}>
            <span className={ttsFieldLabelClass}>
              {t('devSettingPanython.ttsCapabilityDialect')}:
            </span>
            <select
              className={ttsSelectClass}
              value={String(Boolean(settings.supports_dialect))}
              onChange={(event) =>
                updateSetting('supports_dialect', event.target.value === 'true')
              }
            >
              {ttsBooleanOptions.map(([value, optionLabel]) => (
                <option key={value} value={value}>
                  {t(optionLabel)}
                </option>
              ))}
            </select>
          </label>

          <label className={ttsFieldRowClass}>
            <span className={ttsFieldLabelClass}>
              {t('devSettingPanython.defaultDialect')}:
            </span>
            <select
              className={ttsSelectClass}
              value={settings.default_dialect}
              onChange={(event) =>
                updateSetting('default_dialect', event.target.value)
              }
              disabled={!settings.supports_dialect}
            >
              {ttsDialectOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {t(label)}
                </option>
              ))}
            </select>
          </label>

          {capabilityItems.map(([key, label]) => (
            <label key={key} className={ttsFieldRowClass}>
              <span className={ttsFieldLabelClass}>{t(label)}:</span>
              <select
                className={ttsSelectClass}
                value={String(Boolean(settings[key]))}
                onChange={(event) =>
                  updateSetting(key, (event.target.value === 'true') as never)
                }
              >
                {ttsBooleanOptions.map(([value, optionLabel]) => (
                  <option key={value} value={value}>
                    {t(optionLabel)}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </section>

      <section className="mt-5 grid gap-x-8 gap-y-3 md:grid-cols-2">
        <label className={ttsFieldRowClass}>
          <span className={ttsFieldLabelClass}>
            {t('devSettingPanython.defaultEmotion')}:
          </span>
          <select
            className={ttsSelectClass}
            value={settings.default_emotion}
            onChange={(event) =>
              updateSetting('default_emotion', event.target.value)
            }
            disabled={!settings.supports_emotion}
          >
            {ttsEmotionOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {t(label)}
              </option>
            ))}
          </select>
        </label>

        <label className={ttsFieldRowClass}>
          <span className={ttsFieldLabelClass}>
            {t('devSettingPanython.defaultGender')}:
          </span>
          <select
            className={ttsSelectClass}
            value={settings.default_gender}
            onChange={(event) =>
              updateSetting('default_gender', event.target.value)
            }
          >
            <option value="female">
              {t('devSettingPanython.genderFemale')}
            </option>
            <option value="male">{t('devSettingPanython.genderMale')}</option>
          </select>
        </label>

        <label className={ttsFieldRowClass}>
          <span className={ttsFieldLabelClass}>
            {t('devSettingPanython.defaultVoiceProfile')}:
          </span>
          <select
            className={ttsSelectClass}
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
                {t('devSettingPanython.currentVoiceProfile', {
                  profile: settings.default_voice_profile,
                })}
              </option>
            )}
            {ttsVoiceProfileOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {t(label)}
              </option>
            ))}
          </select>
        </label>

        <label className={ttsFieldRowClass}>
          <span className={ttsFieldLabelClass}>
            {t('devSettingPanython.bufferMs')}:
            <TtsHelpButton text={t('devSettingPanython.bufferMsHelp')} />
          </span>
          <select
            className={ttsSelectClass}
            value={settings.buffer_ms}
            onChange={(event) =>
              updateSetting('buffer_ms', Number(event.target.value))
            }
            disabled={!settings.supports_sync_caption}
          >
            {!ttsBufferOptions.includes(settings.buffer_ms) && (
              <option value={settings.buffer_ms}>
                {t('devSettingPanython.bufferMsValue', {
                  value: settings.buffer_ms,
                })}
              </option>
            )}
            {ttsBufferOptions.map((value) => (
              <option key={value} value={value}>
                {t('devSettingPanython.bufferMsValue', { value })}
              </option>
            ))}
          </select>
        </label>

        <label className={ttsFieldRowClass}>
          <span className={ttsFieldLabelClass}>
            {t('devSettingPanython.zhSegmentChars')}:
            <TtsHelpButton text={t('devSettingPanython.zhSegmentCharsHelp')} />
          </span>
          <select
            className={ttsSelectClass}
            value={settings.segment_max_chars_zh}
            onChange={(event) =>
              updateSetting('segment_max_chars_zh', Number(event.target.value))
            }
          >
            {!ttsZhSegmentOptions.includes(settings.segment_max_chars_zh) && (
              <option value={settings.segment_max_chars_zh}>
                {t('devSettingPanython.zhSegmentCharsValue', {
                  value: settings.segment_max_chars_zh,
                })}
              </option>
            )}
            {ttsZhSegmentOptions.map((value) => (
              <option key={value} value={value}>
                {t('devSettingPanython.zhSegmentCharsValue', { value })}
              </option>
            ))}
          </select>
        </label>

        <label className={ttsFieldRowClass}>
          <span className={ttsFieldLabelClass}>
            {t('devSettingPanython.enSegmentWords')}:
            <TtsHelpButton text={t('devSettingPanython.enSegmentWordsHelp')} />
          </span>
          <select
            className={ttsSelectClass}
            value={settings.segment_max_words_en}
            onChange={(event) =>
              updateSetting('segment_max_words_en', Number(event.target.value))
            }
          >
            {!ttsEnSegmentOptions.includes(settings.segment_max_words_en) && (
              <option value={settings.segment_max_words_en}>
                {t('devSettingPanython.enSegmentWordsValue', {
                  value: settings.segment_max_words_en,
                })}
              </option>
            )}
            {ttsEnSegmentOptions.map((value) => (
              <option key={value} value={value}>
                {t('devSettingPanython.enSegmentWordsValue', { value })}
              </option>
            ))}
          </select>
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
          {t('devSettingPanython.preview')}
        </ButtonLoading>
        <ButtonLoading
          type="button"
          loading={saving}
          onClick={handleSave}
          className="bg-[#6f3f2f] text-white dark:bg-[#2d5f80]"
        >
          {t('devSettingPanython.saveTts')}
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
        <Link to={entry.path}>{t('devSettingPanython.open')}</Link>
      </Button>
    </article>
  );
}

export default function DevSettingPanython() {
  const { t } = useTranslation();

  useEffect(() => {
    window.sessionStorage.setItem(DEV_FEATURE_SESSION_KEY, '1');
  }, []);

  return (
    <section className="h-full min-h-0 overflow-y-auto px-4 py-8">
      <div className="mx-auto max-w-7xl">
        <header className="mb-8">
          <h1 className="text-2xl font-semibold text-text-primary">
            {t('devSettingPanython.pageTitle')}
          </h1>
          <p className="mt-2 text-sm text-text-secondary">
            {t('devSettingPanython.pageDescription')}
          </p>
        </header>

        <Tabs defaultValue="menus" className="w-full">
          <TabsList className="mb-4 grid w-full grid-cols-5 lg:w-[760px]">
            <TabsTrigger value="menus">
              {t('devSettingPanython.tabMenus')}
            </TabsTrigger>
            <TabsTrigger value="tts">
              {t('devSettingPanython.tabTts')}
            </TabsTrigger>
            <TabsTrigger value="users">
              {t('devSettingPanython.tabUsers')}
            </TabsTrigger>
            <TabsTrigger value="tenants">
              {t('devSettingPanython.tabTenants')}
            </TabsTrigger>
            <TabsTrigger value="logs">
              {t('devSettingPanython.tabLogs')}
            </TabsTrigger>
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

          <TabsContent value="logs">
            <OperationLogsCard />
          </TabsContent>
        </Tabs>
      </div>
    </section>
  );
}
