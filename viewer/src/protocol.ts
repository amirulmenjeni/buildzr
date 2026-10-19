// The embed protocol (docs/ui-settings.md, "Embed the viewer"): pure parsing and validation, no side effects.
import type { BuildInfo } from './types';

export type ThemeChoice = 'system' | 'light' | 'dark';
export const THEMES: readonly ThemeChoice[] = ['system', 'light', 'dark'];
export const isTheme = (v: unknown): v is ThemeChoice => typeof v === 'string' && (THEMES as readonly string[]).includes(v);

/** The data folder of a built workspace: path relative to data/ -> JSON text or parsed JSON. */
export type Files = Record<string, unknown>;

export interface Mode {
  embed: boolean;
  data: 'message' | 'server'; // embed only: data by `buildzr:load`, or fetched from data/ like the standalone viewer
  theme: ThemeChoice | null; // embed only: the theme the parent asked for in the URL
}

/** Read the mode from the search part of the URL (the hash is the route and is not looked at). */
export function parseMode(search: string): Mode {
  const q = new URLSearchParams(search);
  const embed = q.get('embed') === '1';
  const t = q.get('theme');
  return {
    embed,
    data: embed && q.get('data') === 'server' ? 'server' : 'message',
    theme: embed && isTheme(t) ? t : null,
  };
}

export type InMsg =
  | { type: 'buildzr:load'; files: Files; build: BuildInfo | null; route: string | null; title: string | null }
  | { type: 'buildzr:theme'; theme: ThemeChoice }
  | { type: 'buildzr:route'; route: string };

const isObj = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v);
const isRoute = (v: unknown): v is string => typeof v === 'string' && v.length <= 4096 && (v === '' || v.startsWith('#'));
const optStr = (v: unknown): string | null | undefined => (v === undefined || v === null ? null : typeof v === 'string' ? v.slice(0, 200) : undefined);

/** Files must hold index.json; every value is JSON text or a JSON object/array. */
function files(v: unknown): Files | null {
  if (!isObj(v) || !Object.prototype.hasOwnProperty.call(v, 'index.json')) return null;
  for (const [k, x] of Object.entries(v)) {
    if (!k || k.length > 512) return null;
    if (typeof x !== 'string' && (x === null || typeof x !== 'object')) return null;
  }
  return v;
}
const build = (v: unknown): BuildInfo | null | undefined => (v === undefined || v === null ? null : isObj(v) ? (v as BuildInfo) : undefined);

/** A message of the protocol, checked field by field, or null (unknown type, wrong field types). */
export function parseMessage(d: unknown): InMsg | null {
  if (!isObj(d) || typeof d.type !== 'string') return null;
  switch (d.type) {
    case 'buildzr:load': {
      const f = files(d.files), b = build(d.build), title = optStr(d.title);
      const route = d.route === undefined || d.route === null ? null : isRoute(d.route) ? d.route : undefined;
      if (!f || b === undefined || title === undefined || route === undefined) return null;
      return { type: d.type, files: f, build: b, route, title };
    }
    case 'buildzr:theme':
      return isTheme(d.theme) ? { type: d.type, theme: d.theme } : null;
    case 'buildzr:route':
      return isRoute(d.route) ? { type: d.type, route: d.route } : null;
    default:
      return null;
  }
}

/** The origin rule: same origin, and from the one window we talk to. Never a wildcard. */
export const trusted = (e: { origin: string; source: unknown }, from: unknown, origin: string): boolean =>
  from !== null && from !== undefined && e.source === from && e.origin === origin && origin !== 'null';

