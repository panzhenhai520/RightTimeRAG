import type { IMemory } from './interface';

export type CanonicalTopic = {
  id: string;
  label: string;
  aliases: string[];
  language: string;
  confidence: number;
};

type TopicRule = {
  id: string;
  label: string;
  aliases: string[];
  language: string;
  triggers: RegExp[];
  positiveContext?: RegExp[];
  negativeContext?: RegExp[];
};

const TOPIC_RULES: TopicRule[] = [
  {
    id: 'company:apple',
    label: 'Apple Inc.',
    aliases: ['Apple', 'Apple Inc.', '苹果', '苹果公司', 'AAPL'],
    language: 'multi',
    triggers: [/apple\b/i, /苹果公司?/, /\baapl\b/i],
    positiveContext: [
      /公司|企业|股票|股价|财报|市值|iphone|ipad|macbook|aapl/i,
      /inc\.?|company|stock|share|earnings|market cap|iphone|ipad|macbook/i,
    ],
    negativeContext: [
      /水果|果汁|果园|吃|食物|营养/i,
      /fruit|juice|orchard|eat|food/i,
    ],
  },
  {
    id: 'fruit:apple',
    label: 'Apple fruit',
    aliases: ['apple', '苹果', '苹果水果'],
    language: 'multi',
    triggers: [/apple\b/i, /苹果/],
    positiveContext: [
      /水果|果汁|果园|吃|食物|营养/i,
      /fruit|juice|orchard|eat|food/i,
    ],
    negativeContext: [/公司|股票|股价|财报|iphone|ipad|macbook|aapl/i],
  },
  {
    id: 'topic:family-office',
    label: 'Family office',
    aliases: ['Family office', '家族办公室', '家办', '单一家族办公室'],
    language: 'multi',
    triggers: [/family office/i, /家族办公室|家办|单一家族办公室/],
  },
  {
    id: 'topic:trust-law',
    label: 'Trust law',
    aliases: ['Trust law', 'trust', '信托', '受托人', '受托人条例'],
    language: 'multi',
    triggers: [
      /trustee|trust law|trust ordinance|covenant|rentcharge/i,
      /信托|受托人|契诺|租金|批地|租约/,
    ],
    positiveContext: [
      /法律|条例|责任|契诺|租金|租约|批地|受托人/i,
      /law|ordinance|liability|covenant|rent|lease|trustee/i,
    ],
  },
  {
    id: 'topic:zong-qinghou',
    label: '宗庆后',
    aliases: ['宗庆后', 'Zong Qinghou', 'Wahaha', '娃哈哈'],
    language: 'multi',
    triggers: [/宗庆后|娃哈哈/i, /zong qinghou|wahaha/i],
  },
];

const STOP_WORDS = new Set([
  'the',
  'and',
  'for',
  'with',
  'about',
  'this',
  'that',
  'from',
  'into',
  'what',
  'which',
  'how',
  'why',
  'are',
  'was',
  'were',
  '请问',
  '关于',
  '什么',
  '哪些',
  '如何',
  '是否',
  '这个',
  '那个',
  '用户',
  '问题',
]);

export function normalizeTopicText(text: string) {
  return text
    .toLowerCase()
    .replace(/[_\s]+/g, ' ')
    .replace(/[^\p{Script=Han}a-z0-9\s.-]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function extractTopicKeywords(text: string, limit = 10) {
  const matches = text.match(
    /[\p{Script=Han}]{2,}|[A-Za-z][A-Za-z0-9.-]{2,}/gu,
  );
  const keywords = (matches || [])
    .map(normalizeTopicText)
    .filter((x) => x.length > 1 && !STOP_WORDS.has(x))
    .slice(0, limit);

  return Array.from(new Set(keywords));
}

function ruleMatches(rule: TopicRule, text: string) {
  if (!rule.triggers.some((trigger) => trigger.test(text))) return false;
  if (rule.negativeContext?.some((pattern) => pattern.test(text))) {
    return false;
  }
  if (!rule.positiveContext?.length) return true;
  return rule.positiveContext.some((pattern) => pattern.test(text));
}

function fallbackTopic(text: string): CanonicalTopic {
  const keywords = extractTopicKeywords(text, 4);
  const label = keywords[0] || 'memo';
  return {
    id: `topic:${normalizeTopicText(label).replace(/\s+/g, '-')}`,
    label,
    aliases: keywords,
    language: /[\p{Script=Han}]/u.test(text) ? 'zh' : 'en',
    confidence: 0.45,
  };
}

export function inferCanonicalTopic(text: string): CanonicalTopic {
  const normalized = normalizeTopicText(text);
  const matchedRule = TOPIC_RULES.find((rule) => ruleMatches(rule, normalized));
  if (matchedRule) {
    return {
      id: matchedRule.id,
      label: matchedRule.label,
      aliases: matchedRule.aliases,
      language: matchedRule.language,
      confidence: 0.9,
    };
  }

  return fallbackTopic(normalized || text);
}

export function getCanonicalTopicFromMemory(
  memory: Partial<IMemory>,
  fallbackText: string,
): CanonicalTopic {
  const topic = memory.canonical_topic;
  if (
    topic?.id &&
    topic?.label &&
    Array.isArray(topic.aliases) &&
    typeof topic.confidence === 'number'
  ) {
    return {
      id: topic.id,
      label: topic.label,
      aliases: topic.aliases,
      language: topic.language || 'unknown',
      confidence: topic.confidence,
    };
  }

  return inferCanonicalTopic(fallbackText);
}

export function getMemoryTopicText(
  memory: Partial<IMemory>,
  displayName: string,
) {
  const structuredSummary = memory.structured_summary;
  return [
    structuredSummary?.canonical_topic_candidate,
    structuredSummary?.display_title,
    ...(structuredSummary?.aliases ?? []),
    ...(structuredSummary?.entities?.map((entity) => entity.text) ?? []),
    ...(structuredSummary?.facts?.map((fact) => fact.text) ?? []),
    displayName,
    memory.display_name,
    memory.description,
    memory.latest_content_preview,
    memory.name,
  ]
    .filter(Boolean)
    .join(' ');
}
