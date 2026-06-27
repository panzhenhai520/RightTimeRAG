import {
  currentReg,
  normalizeCitationDigits,
  parseCitationIndex,
} from '@/utils/chat';

const displayReferenceReg =
  /(?:\bfig(?:ure)?\.?\s*|图\s*)([0-9\u0660-\u0669\u06F0-\u06F9]+)/gi;

export const extractNumbersFromMessageContent = (content: string) => {
  const indexes = new Set<number>();
  const matches = content.match(new RegExp(currentReg.source, 'g'));
  if (matches) {
    matches
      .map((match) => {
        const parsed = parseCitationIndex(match);
        return Number.isNaN(parsed) ? null : parsed;
      })
      .filter((num) => num !== null)
      .forEach((num) => indexes.add(num as number));
  }

  for (const match of content.matchAll(new RegExp(displayReferenceReg))) {
    const parsed = Number(normalizeCitationDigits(match[1]));
    if (Number.isFinite(parsed) && parsed > 0) {
      indexes.add(parsed - 1);
    }
  }

  return Array.from(indexes);
};
