export interface Brand {
  name: string;
  subtitle: string;
  mark: string;
}

export interface Batch {
  name: 'current' | 'december';
  mode: 'fixture' | 'full';
  as_of: string;
  inputs: Array<{ file: string; sha256: string; start: string; end: string; fee_available: boolean }>;
  zone_lookup_sha256: string;
}

export interface Summary {
  trips: number;
  fee_cents: number | null;
  has_fee: 0 | 1;
  present_fees: number;
  null_fees: number;
  negative_fees: number;
}

export interface Report {
  backend: string;
  live: boolean;
  batch: Batch;
  revision: string;
  focus: Record<string, Summary | null>;
}

export type Grain = 'month' | 'day' | 'zone';

export interface Row {
  grain: Grain;
  month: string;
  day: string | null;
  zone: number | null;
  zone_name: string | null;
  old: Summary | null;
  candidate: Summary | null;
  fee_difference: number | null;
  trip_difference: number | null;
  issues: string[];
}

export interface Comparison {
  passed: boolean;
  blockers: string[];
  checks: Record<Grain, { groups: number; failed: number }>;
  rows: Row[];
  mismatches: Row[];
  source: Report;
  candidate: Report;
}

export type Phase = 'ready' | 'pending' | 'blocked' | 'approved' | 'switched' | 'fallback' | 'unavailable';

export interface State {
  brand: Brand;
  version: number;
  mode: 'fixture' | 'full';
  target: string;
  targets: Record<string, string>;
  scenario: string;
  scenarios: Record<string, string>;
  batch: Batch;
  phase: Phase;
  detail: string;
  approval: string | null;
  comparison: Comparison | null;
  report: Report | null;
  recovery: { kind: string; reason: string; milliseconds: number | null; batch: string | null } | null;
  events: Array<{ time: string; label: string; backend: string | null; batch: string | null; revision: string | null; note: string }>;
}

export const headline = '2025-01-06';
export const grains: Grain[] = ['month', 'day', 'zone'];
export const grainLabels = { month: 'Month', day: 'Day', zone: 'Pickup zone' };
export const phaseLabels: Record<Phase, string> = {
  ready: 'Ready to check', pending: 'Checks pending', blocked: 'Switch blocked',
  approved: 'Ready for approval', switched: 'Switch approved', fallback: 'Serving fallback',
  unavailable: 'Report unavailable',
};
export const batchNames = { current: 'Dec + Jan', december: 'December only' };
const number = new Intl.NumberFormat('en-US');
const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const date = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' });
const month = new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });

export const count = (value?: number | null) => value == null ? '—' : number.format(value);
export const money = (cents?: number | null) => cents == null ? '—' : usd.format(cents / 100).replace('-', '−');
export const dayLabel = (value: string) => date.format(new Date(value + 'T00:00:00Z'));
export const monthLabel = (value: string) => month.format(new Date(value + 'T00:00:00Z'));
export const lastDay = (value: string) => date.format(new Date(Date.parse(value) - 86_400_000));
export const signed = (value: number | null, format: (value: number) => string) => (
  value == null ? '—' : (value > 0 ? '+' : '') + format(value).replace('-', '−')
);
