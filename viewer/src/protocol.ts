// The embed protocol (docs/ui-settings.md, "Embed the viewer"): pure parsing and validation, no side effects.
import type { BuildInfo } from './types';

export type ThemeChoice = 'system' | 'light' | 'dark';
export const THEMES: readonly ThemeChoice[] = ['system', 'light', 'dark'];
export const isTheme = (v: unknown): v is ThemeChoice => typeof v === 'string' && (THEMES as readonly string[]).includes(v);

/** The data folder of a built workspace: path relative to data/ -> JSON text or parsed JSON. */
export type Files = Record<string, unknown>;

/** One workspace of a `buildzr:load` that carries several: the reader picks among them in the viewer. */
export interface WorkspaceData { name: string; files: Files; build: BuildInfo | null; route: string | null }
/** The workspaces an embedding page sent, and the one that is shown. */
export interface WorkspaceSet { workspaces: WorkspaceData[]; active: string }
export const MAX_WORKSPACES = 50;

export interface Mode {
  embed: boolean;
  data: 'message' | 'server'; // embed only: data by `buildzr:load`, or fetched from data/ like the standalone viewer
  theme: ThemeChoice | null; // embed only: the theme the parent asked for in the URL
  handoff: string | null; // a new tab opened by "Open in a new tab": the id to ask the opener for
}

const HANDOFF_ID = /^[0-9a-f]{32}$/;

/** Read the mode from the search part of the URL (the hash is the route and is not looked at). */
export function parseMode(search: string): Mode {
  const q = new URLSearchParams(search);
  const embed = q.get('embed') === '1';
  const t = q.get('theme');
  const h = q.get('handoff');
  return {
    embed,
    data: embed && q.get('data') === 'server' ? 'server' : 'message',
    theme: embed && isTheme(t) ? t : null,
    handoff: !embed && h && HANDOFF_ID.test(h) ? h : null,
  };
}

export type InMsg =
  // `group` is set when the message carries `workspaces`: files, build and route are then those of the active one
  | { type: 'buildzr:load'; files: Files; build: BuildInfo | null; route: string | null; title: string | null; group: WorkspaceSet | null }
  | { type: 'buildzr:theme'; theme: ThemeChoice }
  | { type: 'buildzr:route'; route: string }
  | { type: 'buildzr:handoff-request'; id: string }
  | { type: 'buildzr:handoff'; id: string; files: Files; build: BuildInfo | null; title: string | null; group: WorkspaceSet | null }
  | { type: 'buildzr:handoff-missing'; id: string };

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

/** `workspaces` (1 to 50 entries with distinct names) and `active` (default: the first). `undefined`: invalid. */
function workspaceSet(list: unknown, active: unknown): WorkspaceSet | null | undefined {
  if (list === undefined || list === null) return null;
  if (!Array.isArray(list) || list.length === 0 || list.length > MAX_WORKSPACES) return undefined;
  const out: WorkspaceData[] = [];
  for (const w of list as unknown[]) {
    if (!isObj(w) || typeof w.name !== 'string' || !w.name || w.name.length > 200) return undefined;
    const f = files(w.files), b = build(w.build);
    const route = w.route === undefined || w.route === null ? null : isRoute(w.route) ? w.route : undefined;
    if (!f || b === undefined || route === undefined || out.some((x) => x.name === w.name)) return undefined;
    out.push({ name: w.name, files: f, build: b, route });
  }
  if (active !== undefined && active !== null && !out.some((x) => x.name === active)) return undefined;
  return { workspaces: out, active: typeof active === 'string' ? active : out[0].name };
}

const activeOf = (g: WorkspaceSet): WorkspaceData => g.workspaces.find((w) => w.name === g.active)!;

/** A message of the protocol, checked field by field, or null (unknown type, wrong field types). */
export function parseMessage(d: unknown): InMsg | null {
  if (!isObj(d) || typeof d.type !== 'string') return null;
  switch (d.type) {
    case 'buildzr:load': {
      const title = optStr(d.title);
      const route = d.route === undefined || d.route === null ? null : isRoute(d.route) ? d.route : undefined;
      const group = workspaceSet(d.workspaces, d.active);
      if (title === undefined || route === undefined || group === undefined) return null;
      if (group) { // the active workspace's data is the data; the message's own route wins over its route
        const a = activeOf(group);
        return { type: d.type, files: a.files, build: a.build, route: route ?? a.route, title, group };
      }
      const f = files(d.files), b = build(d.build);
      if (!f || b === undefined) return null;
      return { type: d.type, files: f, build: b, route, title, group: null };
    }
    case 'buildzr:theme':
      return isTheme(d.theme) ? { type: d.type, theme: d.theme } : null;
    case 'buildzr:route':
      return isRoute(d.route) ? { type: d.type, route: d.route } : null;
    case 'buildzr:handoff-request':
    case 'buildzr:handoff-missing':
      return typeof d.id === 'string' && HANDOFF_ID.test(d.id) ? { type: d.type, id: d.id } : null;
    case 'buildzr:handoff': {
      const title = optStr(d.title);
      const group = workspaceSet(d.workspaces, d.active);
      if (typeof d.id !== 'string' || !HANDOFF_ID.test(d.id) || title === undefined || group === undefined) return null;
      if (group) {
        const a = activeOf(group);
        return { type: d.type, id: d.id, files: a.files, build: a.build, title, group };
      }
      const f = files(d.files), b = build(d.build);
      if (!f || b === undefined) return null;
      return { type: d.type, id: d.id, files: f, build: b, title, group: null };
    }
    default:
      return null;
  }
}

/** The origin rule: same origin, and from the one window we talk to. Never a wildcard. */
export const trusted = (e: { origin: string; source: unknown }, from: unknown, origin: string): boolean =>
  from !== null && from !== undefined && e.source === from && e.origin === origin && origin !== 'null';

/** 32 hex characters from the platform's random source (crypto.randomUUID needs a secure context; this does not). */
export function newId(): string {
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
}
