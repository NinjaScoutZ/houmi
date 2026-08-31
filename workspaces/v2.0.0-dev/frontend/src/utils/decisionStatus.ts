import type { DecisionStatus, TypesettingSpec } from './typesetting';
import { isValidCanonicalSpec } from './typesetting';

export interface DecisionBadge {
  status: DecisionStatus | 'NO_SPEC' | 'STALE';
  label: string;
  short: string;
  /** Tailwind-ish class fragments for chips */
  chipClass: string;
  /** Hex stroke for canvas overlay */
  stroke: string;
  title: string;
}

const BADGES: Record<DecisionStatus, Omit<DecisionBadge, 'status'>> = {
  AUTO_APPLIED: {
    label: 'Auto',
    short: 'OK',
    chipClass: 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300',
    stroke: '#34d399',
    title: 'AUTO_APPLIED — confidence สูงและผ่าน hard constraints',
  },
  DEFAULTED: {
    label: 'Default',
    short: 'DEF',
    chipClass: 'bg-sky-500/15 border-sky-500/40 text-sky-300',
    stroke: '#38bdf8',
    title: 'DEFAULTED — confidence ต่ำ ใช้ template ปลอดภัย',
  },
  NEEDS_REVIEW: {
    label: 'Review',
    short: 'REV',
    chipClass: 'bg-amber-500/15 border-amber-500/40 text-amber-300',
    stroke: '#fbbf24',
    title: 'NEEDS_REVIEW — เสี่ยง overflow / style / font — ต้องตรวจ',
  },
};

export function resolveDecisionBadge(spec: unknown): DecisionBadge {
  if (!spec || typeof spec !== 'object') {
    return {
      status: 'NO_SPEC',
      label: '—',
      short: '—',
      chipClass: 'bg-zinc-800/80 border-zinc-700 text-slate-500',
      stroke: '#71717a',
      title: 'ยังไม่มี TypesettingSpec',
    };
  }
  const s = spec as Partial<TypesettingSpec> & { layout_status?: string };
  if (s.layout_status === 'stale' || !isValidCanonicalSpec(spec)) {
    return {
      status: 'STALE',
      label: 'Stale',
      short: 'ST',
      chipClass: 'bg-zinc-800/80 border-zinc-600 text-slate-400',
      stroke: '#a1a1aa',
      title: 'Spec หมดอายุหรือไม่ตรง engine — จะ recompute อัตโนมัติ',
    };
  }
  const status = (s.decision_status || 'AUTO_APPLIED') as DecisionStatus;
  const base = BADGES[status] || BADGES.AUTO_APPLIED;
  return { status, ...base };
}

export function countDecisions(
  blocks: Array<{ translation?: string | null; extra_metadata?: { typesetting_spec?: unknown } | null }>,
): Record<string, number> {
  const counts: Record<string, number> = {
    AUTO_APPLIED: 0,
    DEFAULTED: 0,
    NEEDS_REVIEW: 0,
    STALE: 0,
    NO_SPEC: 0,
    with_text: 0,
  };
  for (const block of blocks) {
    if (!block.translation?.trim()) continue;
    counts.with_text += 1;
    const badge = resolveDecisionBadge(block.extra_metadata?.typesetting_spec);
    counts[badge.status] = (counts[badge.status] || 0) + 1;
  }
  return counts;
}

export type LayerDecisionFilter = 'all' | 'NEEDS_REVIEW' | 'DEFAULTED' | 'AUTO_APPLIED' | 'STALE';

/** Review Queue filter — keep blocks matching decision status (or all). */
export function filterBlocksByDecision<
  T extends { translation?: string | null; extra_metadata?: { typesetting_spec?: unknown } | null },
>(blocks: T[], filter: LayerDecisionFilter): T[] {
  if (filter === 'all') return blocks;
  // After the early return, filter is narrowed away from 'all' — do not compare to 'all' again (TS2367).
  return blocks.filter((b) => {
    // Empty translation never enters style/layout review queues
    if (!b.translation?.trim()) {
      return false;
    }
    return resolveDecisionBadge(b.extra_metadata?.typesetting_spec).status === filter;
  });
}
