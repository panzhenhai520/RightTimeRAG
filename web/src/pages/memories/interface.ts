export interface CreateMemoryResponse {
  id: string;
  name: string;
  description: string;
}

export interface MemoryListParams {
  keywords?: string;
  parser_id?: string;
  page?: number;
  page_size?: number;
  orderby?: string;
  desc?: boolean;
  owner_ids?: string;
}
export type MemoryType = 'raw' | 'semantic' | 'episodic' | 'procedural';
export type StorageType = 'table' | 'graph';
export type Permissions = 'me' | 'team';
export type ForgettingPolicy = 'FIFO' | 'LRU';
export interface IMemoryStructuredSummary {
  display_title?: string;
  canonical_topic_candidate?: string;
  aliases?: string[];
  language?: string;
  entities?: Array<{ text: string; label: string; normalized?: string }>;
  dates?: string[];
  amounts?: Array<{ text: string; normalized?: string }>;
  facts?: Array<{ text: string; source_message_ids?: string[] }>;
  open_questions?: string[];
  source_message_ids?: string[];
  related_kb_ids?: string[];
}
export interface ICanonicalTopic {
  id: string;
  label: string;
  aliases: string[];
  language: string;
  confidence: number;
}
export interface ICreateMemoryProps {
  name: string;
  memory_type: MemoryType[];
  embd_id: string;
  llm_id: string;
}
export interface IMemory extends ICreateMemoryProps {
  id: string;
  display_name?: string;
  is_chat_memo?: boolean;
  latest_content_preview?: string;
  latest_forget_at?: string | null;
  latest_agent_id?: string;
  latest_session_id?: string;
  structured_summary?: IMemoryStructuredSummary;
  canonical_topic?: ICanonicalTopic;
  message_count?: number;
  avatar: string;
  tenant_id: string;
  owner_name: string;
  storage_type: StorageType;
  permissions: Permissions;
  description: string;
  memory_size: number;
  forgetting_policy: ForgettingPolicy;
  temperature: string;
  system_prompt: string;
  user_prompt: string;
  create_date: string;
  create_time: number;
}
export interface MemoryListResponse {
  code: number;
  data: {
    memory_list: Array<IMemory>;
    total_count: number;
  };
  message: string;
}

export interface IMemoThoughtEvidence {
  type: string;
  memory_id: string;
  title: string;
  snippet: string;
}

export interface IMemoThoughtEvent {
  id: string;
  memory_id: string;
  title: string;
  summary: string;
  created_at: number;
  topic_id: string;
  topic_label: string;
  original_topic_id?: string;
  original_topic_label?: string;
  domain: string;
  domain_label: string;
  intent: string;
  intent_label: string;
  keywords: string[];
  turns: number;
  source_kind: string;
  assistant_id?: string;
  session_id?: string;
  related_kb_ids: string[];
  evidence: IMemoThoughtEvidence[];
  confidence: number;
}

export interface IMemoThoughtTopic {
  id: string;
  label: string;
  domain: string;
  domain_label: string;
  event_ids: string[];
  source_topic_ids?: string[];
  keywords: string[];
  memo_count: number;
  turn_count: number;
  first_seen: number;
  last_seen: number;
  activity_score: number;
}

export interface IMemoThoughtEdge {
  id: string;
  source_event_id: string;
  target_event_id: string;
  source_topic_id: string;
  target_topic_id: string;
  type: string;
  weight: number;
  shared_signals: string[];
  evidence_event_ids: string[];
  reason: string;
  score_parts: Record<string, number>;
}

export interface IMemoThoughtPrediction {
  question: string;
  reason: string;
  evidence_event_ids: string[];
  topics: string[];
}

export interface IMemoThoughtAlgorithmNote {
  title: string;
  authors: string;
  url?: string;
  borrowed: string;
}

export interface IMemoTopicMergeRule {
  target_topic_id: string;
  target_label: string;
  reason: string;
  created_at?: number;
}

export interface IMemoTopicMerges {
  version: string;
  rules: Record<string, IMemoTopicMergeRule>;
  updated_at: number;
}

export interface IMemoTopicMergeSuggestion {
  source_topic_ids: string[];
  target_topic_id: string;
  target_label: string;
  source_label: string;
  semantic_score: number;
  keyword_score: number;
  confidence: number;
  shared_signals: string[];
  evidence_event_ids: string[];
  reason: string;
}

export interface IMemoThoughtProfile {
  version: string;
  status: 'ready' | 'empty' | 'pending' | 'building' | 'error' | 'disabled';
  feature_enabled?: boolean;
  semantic_model?: string;
  generated_at: number;
  duration_ms?: number;
  stale?: boolean;
  memory_count: number;
  event_count: number;
  summary: {
    headline: string;
    trajectory: string;
    next_direction: string;
    focus_domains: Array<{ id: string; label: string; count: number }>;
  };
  events: IMemoThoughtEvent[];
  topics: IMemoThoughtTopic[];
  topic_merges?: IMemoTopicMerges;
  topic_merge_suggestions?: IMemoTopicMergeSuggestion[];
  edges: IMemoThoughtEdge[];
  predictions: IMemoThoughtPrediction[];
  algorithm_notes: IMemoThoughtAlgorithmNote[];
}

export interface MemoryProfileResponse {
  code: number;
  data: IMemoThoughtProfile;
  message: string;
}

export interface MergeMemoryProfileTopicsPayload {
  source_topic_ids: string[];
  target_topic_id: string;
  target_label?: string;
  reason?: string;
}

export interface DeleteMemoryProfileTopicMergesPayload {
  source_topic_ids?: string[];
  target_topic_id?: string;
}

export interface MemoryTopicMergesResponse {
  code: number;
  data: IMemoTopicMerges;
  message: string;
}

export interface DeleteMemoryProps {
  memory_id: string;
}

export interface DeleteMemoryResponse {
  code: number;
  data: boolean;
  message: string;
}

export interface IllmSettingProps {
  llm_id: string;
  parameter: string;
  temperature?: number;
  top_p?: number;
  frequency_penalty?: number;
  presence_penalty?: number;
}
interface IllmSettingEnableProps {
  temperatureEnabled?: boolean;
  topPEnabled?: boolean;
  presencePenaltyEnabled?: boolean;
  frequencyPenaltyEnabled?: boolean;
}
export interface IMemoryAppDetailProps {
  avatar: any;
  created_by: string;
  description: string;
  id: string;
  name: string;
  memory_config: {
    cross_languages: string[];
    doc_ids: string[];
    chat_id: string;
    highlight: boolean;
    kb_ids: string[];
    keyword: boolean;
    query_mindmap: boolean;
    related_memory: boolean;
    rerank_id: string;
    use_rerank?: boolean;
    similarity_threshold: number;
    summary: boolean;
    llm_setting: IllmSettingProps & IllmSettingEnableProps;
    top_k: number;
    use_kg: boolean;
    vector_similarity_weight: number;
    web_memory: boolean;
    chat_settingcross_languages: string[];
    meta_data_filter?: {
      method: string;
      manual: { key: string; op: string; value: string }[];
    };
  };
  tenant_id: string;
  update_time: number;
}

export interface MemoryDetailResponse {
  code: number;
  data: IMemoryAppDetailProps;
  message: string;
}

// export type IUpdateMemoryProps = Omit<IMemoryAppDetailProps, 'id'> & {
//   id: string;
// };
