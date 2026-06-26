import { Button, ButtonLoading } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import message from '@/components/ui/message';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useRegister } from '@/hooks/use-login-request';
import { DEV_FEATURE_SESSION_KEY, Routes } from '@/routes';
import { rsaPsw } from '@/utils';
import request from '@/utils/next-request';
import {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
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
  {
    titleKey: 'devSettingPanython.modelManagement',
    descriptionKey: 'devSettingPanython.modelManagementDescription',
    path: `${Routes.UserSetting}${Routes.Model}`,
  },
];

const tenantRelationsApi = '/api/v1/dev/tenant-relations';
const tenantRelationLogsApi = '/api/v1/dev/tenant-relations/logs';
const ttsEngineSettingsApi = '/api/v1/dev/tts-engine-settings';
const asrSettingsApi = '/api/v1/dev/asr-settings';

type AsrSettings = {
  mode: 'single' | 'dual';
  single_model: 'qwen3' | 'sensevoice';
  dual_merge: 'qwen3_primary' | 'sensevoice_primary' | 'longest';
  language: 'auto' | 'zh' | 'yue' | 'en';
  short_audio_threshold_ms: number;
  punctuation: boolean;
  vad: boolean;
};

const defaultAsrSettings: AsrSettings = {
  mode: 'dual',
  single_model: 'qwen3',
  dual_merge: 'qwen3_primary',
  language: 'auto',
  short_audio_threshold_ms: 3000,
  punctuation: false,
  vad: false,
};

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

  const users = useMemo(() => data?.users ?? [], [data?.users]);
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

// ---------------------------------------------------------------------------
// IdentityCard — global assistant identity maintained by admin
// ---------------------------------------------------------------------------

function IdentityCard() {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    request
      .get('/api/v1/dev/identity')
      .then((res) => {
        if (res.data?.code === 0) setText(res.data.data?.text ?? '');
      })
      .catch(() => {});
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const res = await request.post('/api/v1/dev/identity', { text });
      if (res.data?.code === 0) {
        message.success(t('devSettingPanython.identitySaved'));
      }
    } finally {
      setSaving(false);
    }
  }, [text, t]);

  return (
    <article className="mt-4 rounded-lg border border-border bg-bg-card p-5 md:col-span-2">
      <h2 className="text-lg font-medium text-text-primary">
        {t('devSettingPanython.identityTitle')}
      </h2>
      <p className="mt-1 text-sm text-text-secondary">
        {t('devSettingPanython.identityDescription')}
      </p>
      <textarea
        className="mt-4 w-full min-h-[120px] rounded-md border border-border-button bg-bg-input px-3 py-2 text-sm text-text-primary outline-none focus:border-[#6f3f2f] dark:focus:border-[#9bc7dd]"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={t('devSettingPanython.identityPlaceholder')}
      />
      <div className="mt-3 flex justify-end">
        <ButtonLoading
          type="button"
          loading={saving}
          className="bg-[#6f3f2f] text-white dark:bg-[#2d5f80]"
          onClick={handleSave}
        >
          {t('devSettingPanython.identitySaveBtn')}
        </ButtonLoading>
      </div>
    </article>
  );
}

function AsrSettingsCard() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<AsrSettings>(defaultAsrSettings);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await request.get(asrSettingsApi);
      if (res.data?.code === 0) {
        setSettings({ ...defaultAsrSettings, ...res.data.data });
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const update = <K extends keyof AsrSettings>(
    key: K,
    value: AsrSettings[K],
  ) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await request.put(asrSettingsApi, settings);
      if (res.data?.code === 0) {
        setSettings({ ...defaultAsrSettings, ...res.data.data });
        message.success(t('devSettingPanython.asrSaved'));
      }
    } finally {
      setSaving(false);
    }
  };

  const fieldRow =
    'grid grid-cols-[max-content_minmax(200px,280px)] items-center justify-start gap-2 text-sm';
  const fieldLabel =
    'inline-flex items-center gap-1 whitespace-nowrap text-text-secondary';
  const sel =
    'h-9 w-full border-0 border-b border-border-button bg-transparent px-0 pr-8 text-sm text-text-primary outline-none disabled:cursor-not-allowed disabled:opacity-50';

  return (
    <article className="rounded-lg border border-border bg-bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-text-primary">
            {t('devSettingPanython.asrTitle')}
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            {t('devSettingPanython.asrDescription')}
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
        {/* Mode */}
        <label className={fieldRow}>
          <span className={fieldLabel}>{t('devSettingPanython.asrMode')}:</span>
          <select
            className={sel}
            value={settings.mode}
            onChange={(e) =>
              update('mode', e.target.value as AsrSettings['mode'])
            }
          >
            <option value="dual">{t('devSettingPanython.asrModeDual')}</option>
            <option value="single">
              {t('devSettingPanython.asrModeSingle')}
            </option>
          </select>
        </label>

        {/* Single model — only visible in single mode */}
        {settings.mode === 'single' && (
          <label className={fieldRow}>
            <span className={fieldLabel}>
              {t('devSettingPanython.asrSingleModel')}:
            </span>
            <select
              className={sel}
              value={settings.single_model}
              onChange={(e) =>
                update(
                  'single_model',
                  e.target.value as AsrSettings['single_model'],
                )
              }
            >
              <option value="qwen3">
                {t('devSettingPanython.asrModelQwen3')}
              </option>
              <option value="sensevoice">
                {t('devSettingPanython.asrModelSenseVoice')}
              </option>
            </select>
          </label>
        )}

        {/* Dual merge strategy — only visible in dual mode */}
        {settings.mode === 'dual' && (
          <label className={fieldRow}>
            <span className={fieldLabel}>
              {t('devSettingPanython.asrDualMerge')}:
            </span>
            <select
              className={sel}
              value={settings.dual_merge}
              onChange={(e) =>
                update(
                  'dual_merge',
                  e.target.value as AsrSettings['dual_merge'],
                )
              }
            >
              <option value="qwen3_primary">
                {t('devSettingPanython.asrMergeQwen3Primary')}
              </option>
              <option value="sensevoice_primary">
                {t('devSettingPanython.asrMergeSVPrimary')}
              </option>
              <option value="longest">
                {t('devSettingPanython.asrMergeLongest')}
              </option>
            </select>
          </label>
        )}

        {/* Language */}
        <label className={fieldRow}>
          <span className={fieldLabel}>
            {t('devSettingPanython.asrLanguage')}:
          </span>
          <select
            className={sel}
            value={settings.language}
            onChange={(e) =>
              update('language', e.target.value as AsrSettings['language'])
            }
          >
            <option value="auto">{t('devSettingPanython.asrLangAuto')}</option>
            <option value="yue">
              {t('devSettingPanython.asrLangCantonese')}
            </option>
            <option value="zh">
              {t('devSettingPanython.asrLangMandarin')}
            </option>
            <option value="en">{t('devSettingPanython.asrLangEnglish')}</option>
          </select>
        </label>

        {/* Short audio threshold */}
        <label className={fieldRow}>
          <span className={fieldLabel}>
            {t('devSettingPanython.asrShortThreshold')}:
          </span>
          <select
            className={sel}
            value={settings.short_audio_threshold_ms}
            onChange={(e) =>
              update('short_audio_threshold_ms', Number(e.target.value))
            }
          >
            {[1000, 2000, 3000, 5000, 8000].map((ms) => (
              <option key={ms} value={ms}>
                {ms / 1000}s
              </option>
            ))}
          </select>
        </label>

        {/* Punctuation */}
        <label className={fieldRow}>
          <span className={fieldLabel}>
            {t('devSettingPanython.asrPunctuation')}:
            <TtsHelpButton text={t('devSettingPanython.asrPunctuationHelp')} />
          </span>
          <select
            className={sel}
            value={String(settings.punctuation)}
            onChange={(e) => update('punctuation', e.target.value === 'true')}
          >
            <option value="false">
              {t('devSettingPanython.optionDisabled')}
            </option>
            <option value="true">
              {t('devSettingPanython.optionEnabled')}
            </option>
          </select>
        </label>

        {/* VAD */}
        <label className={fieldRow}>
          <span className={fieldLabel}>
            {t('devSettingPanython.asrVad')}:
            <TtsHelpButton text={t('devSettingPanython.asrVadHelp')} />
          </span>
          <select
            className={sel}
            value={String(settings.vad)}
            onChange={(e) => update('vad', e.target.value === 'true')}
          >
            <option value="false">
              {t('devSettingPanython.optionDisabled')}
            </option>
            <option value="true">
              {t('devSettingPanython.optionEnabled')}
            </option>
          </select>
        </label>
      </div>

      {/* Status badges */}
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">
          Qwen3-ASR-1.7B · port 9900 · GPU1
        </span>
        <span className="rounded-full bg-sky-50 px-2 py-0.5 text-sky-700 dark:bg-sky-950/30 dark:text-sky-300">
          SenseVoice · xinference port 9997 · GPU0
        </span>
      </div>

      <div className="mt-5 flex gap-3">
        <ButtonLoading loading={saving} onClick={handleSave}>
          {t('devSettingPanython.identitySaveBtn')}
        </ButtonLoading>
      </div>
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

// ---------------------------------------------------------------------------
// Voice profile types & audio helpers
// ---------------------------------------------------------------------------

type VoiceProfile = {
  id: string;
  mode: string;
  is_custom: boolean;
  display_name: string;
};

function encodePcmToWav(
  samples: Float32Array,
  sampleRate: number,
): ArrayBuffer {
  const n = samples.length;
  const buf = new ArrayBuffer(44 + n * 2);
  const v = new DataView(buf);
  const w = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(off + i, s.charCodeAt(i));
  };
  w(0, 'RIFF');
  v.setUint32(4, 36 + n * 2, true);
  w(8, 'WAVE');
  w(12, 'fmt ');
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true);
  v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true);
  v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  w(36, 'data');
  v.setUint32(40, n * 2, true);
  let off = 44;
  for (let i = 0; i < n; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    off += 2;
  }
  return buf;
}

async function blobToWav16k(blob: Blob): Promise<Blob> {
  const ab = await blob.arrayBuffer();
  const ctx = new AudioContext({ sampleRate: 16000 });
  let decoded: AudioBuffer;
  try {
    decoded = await ctx.decodeAudioData(ab);
  } finally {
    await ctx.close();
  }
  const mono = decoded.getChannelData(0);
  return new Blob([encodePcmToWav(mono, 16000)], { type: 'audio/wav' });
}

// ---------------------------------------------------------------------------
// TtsVoiceProfilesCard — recording + custom voice management
// ---------------------------------------------------------------------------

// Phonetically curated Chinese sentence: covers all 4 tones, retroflex/non-retroflex
// initials, nasal finals, and diverse vowels — ideal for voice cloning reference audio.
const DEFAULT_VOICE_PROMPT =
  '家族信托能帮助高净值家庭实现跨代财富传承与资产保护。投资者应理性评估市场风险，根据自身财务状况，与专业顾问共同制定长期的资产配置方案。';

function TtsVoiceProfilesCard() {
  const { t } = useTranslation();
  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [voiceId, setVoiceId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [promptText, setPromptText] = useState(DEFAULT_VOICE_PROMPT);
  const [recordingState, setRecordingState] = useState<
    'idle' | 'recording' | 'recorded'
  >('idle');
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [wavBlob, setWavBlob] = useState<Blob | null>(null);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const playingRef = useRef<HTMLAudioElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadVoices = useCallback(async () => {
    setLoading(true);
    try {
      const res = await request.get('/api/v1/dev/tts-voices');
      if (res.data?.code === 0) setVoices(res.data.data?.voices ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadVoices();
  }, [loadVoices]);

  useEffect(
    () => () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    },
    [audioUrl],
  );

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const raw = new Blob(chunksRef.current, {
          type: recorder.mimeType || 'audio/webm',
        });
        try {
          const wav = await blobToWav16k(raw);
          if (audioUrl) URL.revokeObjectURL(audioUrl);
          const url = URL.createObjectURL(wav);
          setAudioUrl(url);
          setWavBlob(wav);
          setRecordingState('recorded');
        } catch {
          message.error('Audio conversion failed — please try again.');
          setRecordingState('idle');
        }
      };
      recorder.start();
      mediaRecorderRef.current = recorder;
      let secs = 0;
      setRecordingSeconds(0);
      timerRef.current = setInterval(() => {
        secs++;
        setRecordingSeconds(secs);
      }, 1000);
      setRecordingState('recording');
    } catch (err) {
      const isBlocked =
        err instanceof DOMException &&
        (err.name === 'NotAllowedError' || err.name === 'SecurityError');
      message.error(
        isBlocked
          ? t('devSettingPanython.ttsAddVoiceMicError')
          : 'Microphone error — please check browser permissions.',
      );
    }
  }, [audioUrl, t]);

  const stopRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mediaRecorderRef.current?.state === 'recording')
      mediaRecorderRef.current.stop();
  }, []);

  const resetRecording = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stream?.getTracks().forEach((t) => t.stop());
      mediaRecorderRef.current.stop();
    }
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioUrl(null);
    setWavBlob(null);
    setRecordingState('idle');
    setRecordingSeconds(0);
  }, [audioUrl]);

  const playRecording = useCallback(() => {
    if (!audioUrl) return;
    if (playingRef.current) {
      playingRef.current.pause();
      playingRef.current = null;
    }
    const a = new Audio(audioUrl);
    playingRef.current = a;
    a.play();
  }, [audioUrl]);

  const handleFileUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      e.target.value = '';
      try {
        // measure original duration before resampling
        const ctx = new AudioContext();
        const decoded = await ctx.decodeAudioData(await file.arrayBuffer());
        const secs = Math.round(decoded.duration);
        await ctx.close();
        // convert to 16 kHz mono WAV for CosyVoice3
        const wav = await blobToWav16k(file);
        if (audioUrl) URL.revokeObjectURL(audioUrl);
        setAudioUrl(URL.createObjectURL(wav));
        setWavBlob(wav);
        setRecordingSeconds(secs);
        setRecordingState('recorded');
      } catch {
        message.error('Cannot decode audio file — please try WAV or MP3.');
      }
    },
    [audioUrl],
  );

  const resetForm = useCallback(() => {
    setVoiceId('');
    setDisplayName('');
    setPromptText(DEFAULT_VOICE_PROMPT);
    resetRecording();
  }, [resetRecording]);

  const handleSave = useCallback(async () => {
    if (!wavBlob) {
      message.warning(t('devSettingPanython.ttsAddVoiceNoAudio'));
      return;
    }
    if (recordingSeconds < 3) {
      message.warning(t('devSettingPanython.ttsAddVoiceTooShort'));
      return;
    }
    if (!voiceId.trim()) {
      message.warning('Profile ID is required');
      return;
    }
    if (!promptText.trim()) {
      message.warning('Recording text is required');
      return;
    }

    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('voice_id', voiceId.trim());
      formData.append('display_name', displayName.trim() || voiceId.trim());
      formData.append('prompt_text', promptText.trim());
      formData.append('audio', wavBlob, `${voiceId.trim()}.wav`);
      const res = await request.post('/api/v1/dev/tts-voices', formData);
      if (res.data?.code === 0) {
        message.success(
          t('devSettingPanython.ttsAddVoiceSaved', {
            name: displayName.trim() || voiceId.trim(),
          }),
        );
        setShowAddForm(false);
        resetForm();
        await loadVoices();
      } else {
        message.error(
          t('devSettingPanython.ttsAddVoiceError', {
            error: res.data?.message || 'unknown',
          }),
        );
      }
    } catch (err) {
      message.error(
        t('devSettingPanython.ttsAddVoiceError', { error: String(err) }),
      );
    } finally {
      setSaving(false);
    }
  }, [
    wavBlob,
    recordingSeconds,
    voiceId,
    promptText,
    displayName,
    t,
    resetForm,
    loadVoices,
  ]);

  const handleDelete = useCallback(
    async (v: VoiceProfile) => {
      if (
        !window.confirm(
          t('devSettingPanython.ttsVoiceProfilesDeleteConfirm', {
            name: v.display_name || v.id,
          }),
        )
      )
        return;
      const res = await request.delete(`/api/v1/dev/tts-voices/${v.id}`);
      if (res.data?.code === 0) {
        message.success(t('devSettingPanython.ttsVoiceProfilesDeleted'));
        await loadVoices();
      }
    },
    [t, loadVoices],
  );

  const builtIn = useMemo(() => voices.filter((v) => !v.is_custom), [voices]);
  const custom = useMemo(() => voices.filter((v) => v.is_custom), [voices]);

  return (
    <article className="mt-4 rounded-lg border border-border bg-bg-card p-5 md:col-span-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-text-primary">
            {t('devSettingPanython.ttsVoiceProfilesTitle')}
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            {t('devSettingPanython.ttsVoiceProfilesDescription')}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            loading={loading}
            onClick={loadVoices}
          >
            {t('devSettingPanython.ttsVoiceProfilesRefresh')}
          </Button>
          <Button
            type="button"
            className="bg-[#6f3f2f] text-white dark:bg-[#2d5f80]"
            onClick={() => {
              setShowAddForm((v) => !v);
              if (showAddForm) resetForm();
            }}
          >
            {t('devSettingPanython.ttsVoiceProfilesAdd')}
          </Button>
        </div>
      </div>

      {/* Add voice form */}
      {showAddForm && (
        <div className="mt-5 rounded-lg border border-[#6f3f2f]/40 bg-bg-base/60 p-4 dark:border-[#9bc7dd]/40">
          <h3 className="mb-4 text-base font-semibold text-text-primary">
            {t('devSettingPanython.ttsAddVoiceTitle')}
          </h3>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-text-primary">
                {t('devSettingPanython.ttsAddVoiceId')}
              </span>
              <input
                className="h-9 rounded-md border border-border-button bg-bg-input px-3 text-sm text-text-primary outline-none focus:border-[#6f3f2f] dark:focus:border-[#9bc7dd]"
                placeholder={t('devSettingPanython.ttsAddVoiceIdPlaceholder')}
                value={voiceId}
                onChange={(e) =>
                  setVoiceId(e.target.value.replace(/[^a-zA-Z0-9_]/g, ''))
                }
              />
              <span className="text-xs text-text-secondary">
                {t('devSettingPanython.ttsAddVoiceIdHelp')}
              </span>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-text-primary">
                {t('devSettingPanython.ttsAddVoiceDisplayName')}
              </span>
              <input
                className="h-9 rounded-md border border-border-button bg-bg-input px-3 text-sm text-text-primary outline-none focus:border-[#6f3f2f] dark:focus:border-[#9bc7dd]"
                placeholder={t(
                  'devSettingPanython.ttsAddVoiceDisplayNamePlaceholder',
                )}
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </label>
          </div>

          <label className="mt-3 flex flex-col gap-1 text-sm">
            <span className="font-medium text-text-primary">
              {t('devSettingPanython.ttsAddVoicePromptText')}
            </span>
            <textarea
              className="min-h-[72px] rounded-md border border-border-button bg-bg-input px-3 py-2 text-sm text-text-primary outline-none focus:border-[#6f3f2f] dark:focus:border-[#9bc7dd]"
              placeholder={t(
                'devSettingPanython.ttsAddVoicePromptTextPlaceholder',
              )}
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
            />
            <span className="text-xs text-text-secondary">
              {t('devSettingPanython.ttsAddVoicePromptTextHelp')}
            </span>
          </label>

          {/* Recording controls */}
          <div className="mt-4 flex flex-wrap items-center gap-3">
            {recordingState === 'idle' && (
              <>
                <button
                  type="button"
                  className="inline-flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
                  onClick={startRecording}
                >
                  <span className="text-base">●</span>
                  {t('devSettingPanython.ttsAddVoiceRecord')}
                </button>
                <span className="text-sm text-text-secondary">
                  {t('devSettingPanython.ttsAddVoiceOrUpload')}
                </span>
                <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-border-button px-4 py-2 text-sm font-medium text-text-primary hover:bg-bg-hover">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="audio/*"
                    className="sr-only"
                    onChange={handleFileUpload}
                  />
                  ↑ {t('devSettingPanython.ttsAddVoiceUploadHint')}
                </label>
              </>
            )}
            {recordingState === 'recording' && (
              <button
                type="button"
                className="inline-flex animate-pulse items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white"
                onClick={stopRecording}
              >
                <span className="text-base">■</span>
                {t('devSettingPanython.ttsAddVoiceRecording')}
                <span className="ml-1 font-mono tabular-nums">
                  {recordingSeconds}s
                </span>
              </button>
            )}
            {recordingState === 'recorded' && (
              <>
                <span className="text-sm text-text-secondary">
                  {t('devSettingPanython.ttsAddVoiceRecorded', {
                    seconds: recordingSeconds,
                  })}
                </span>
                <Button type="button" variant="outline" onClick={playRecording}>
                  {t('devSettingPanython.ttsAddVoicePlay')}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={resetRecording}
                >
                  {t('devSettingPanython.ttsAddVoiceReRecord')}
                </Button>
              </>
            )}
          </div>

          <div className="mt-5 flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setShowAddForm(false);
                resetForm();
              }}
            >
              取消
            </Button>
            <ButtonLoading
              type="button"
              loading={saving}
              disabled={
                recordingState !== 'recorded' ||
                !voiceId.trim() ||
                !promptText.trim()
              }
              className="bg-[#6f3f2f] text-white dark:bg-[#2d5f80]"
              onClick={handleSave}
            >
              {saving
                ? t('devSettingPanython.ttsAddVoiceSaving')
                : t('devSettingPanython.ttsAddVoiceSave')}
            </ButtonLoading>
          </div>
        </div>
      )}

      {/* Custom voices list */}
      <section className="mt-5">
        <h3 className="mb-3 text-sm font-semibold text-text-primary">
          {t('devSettingPanython.ttsVoiceProfilesCustom')}
        </h3>
        {custom.length === 0 ? (
          <p className="text-sm text-text-secondary">
            {t('devSettingPanython.ttsVoiceProfilesEmpty')}
          </p>
        ) : (
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {custom.map((v) => (
              <div
                key={v.id}
                className="flex items-center justify-between gap-2 rounded-md border border-[#6f3f2f]/30 bg-[#6f3f2f]/5 px-3 py-2 text-sm dark:border-[#9bc7dd]/30 dark:bg-[#2d5f80]/10"
              >
                <div className="min-w-0">
                  <div className="truncate font-medium text-text-primary">
                    {v.display_name || v.id}
                  </div>
                  <div className="text-xs text-text-secondary">{v.id}</div>
                </div>
                <Button
                  type="button"
                  size="xs"
                  variant="outline"
                  className="shrink-0 border-red-500 text-red-500 hover:bg-red-50 dark:hover:bg-red-950"
                  onClick={() => handleDelete(v)}
                >
                  删除
                </Button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Built-in voices (collapsible) */}
      <details className="mt-5">
        <summary className="cursor-pointer text-sm font-semibold text-text-secondary hover:text-text-primary">
          {t('devSettingPanython.ttsVoiceProfilesBuiltIn')} ({builtIn.length})
        </summary>
        <div className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {builtIn.map((v) => (
            <div
              key={v.id}
              className="rounded-md border border-border/60 bg-bg-base/50 px-3 py-2 text-sm"
            >
              <div className="font-medium text-text-primary">
                {v.display_name || v.id}
              </div>
              <div className="text-xs text-text-secondary">{v.mode}</div>
            </div>
          ))}
        </div>
      </details>
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
          <TabsList className="mb-4 grid w-full grid-cols-7 lg:w-[1050px]">
            <TabsTrigger value="menus">
              {t('devSettingPanython.tabMenus')}
            </TabsTrigger>
            <TabsTrigger value="assistant">
              {t('devSettingPanython.tabAssistant')}
            </TabsTrigger>
            <TabsTrigger value="tts">
              {t('devSettingPanython.tabTts')}
            </TabsTrigger>
            <TabsTrigger value="asr">
              {t('devSettingPanython.tabAsr')}
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

          <TabsContent value="assistant">
            <IdentityCard />
          </TabsContent>

          <TabsContent value="tts">
            <TtsEngineSettingsCard />
            <TtsVoiceProfilesCard />
          </TabsContent>

          <TabsContent value="asr">
            <AsrSettingsCard />
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
