import type { Files } from './protocol';
import type { BuildInfo, IndexJson, ModelJson, Scene } from './types';

/** Where the data comes from: the server (data/ next to index.html), or files an embedding page posted. */
interface Source { build(): Promise<BuildInfo | null>; json<T>(file: string): Promise<T> }

// All URLs are relative to index.html so the site works at / and at a subpath, offline.
const get = async <T,>(url: string): Promise<T> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return (await r.json()) as T;
};
/** Where the list of workspaces is, when `buildzr serve` said so with its X-Buildzr-Workspaces header on build.json. */
let catalogueUrl: string | null = null;
export const getCatalogueUrl = (): string | null => catalogueUrl;
const WORKSPACES_HEADER = 'X-Buildzr-Workspaces';

const server: Source = {
  /** build.json, or null when it cannot be read (an old build, or a host that does not serve it): then all is ok. */
  async build() {
    try {
      const r = await fetch('build.json');
      if (!r.ok) return null;
      const where = r.headers.get(WORKSPACES_HEADER);
      // The header is relative to the workspace's folder; only the origin of this page is ever asked.
      const url = where ? new URL(where, new URL('./', r.url || location.href)) : null;
      catalogueUrl = url && url.origin === location.origin ? url.href : null;
      const b = (await r.json()) as unknown;
      return b && typeof b === 'object' && !Array.isArray(b) ? (b as BuildInfo) : null;
    } catch {
      return null;
    }
  },
  json: (file) => get('data/' + file),
};

/** Files in memory (embed mode, or a new tab handed the data by its opener). A value is JSON text or parsed JSON. */
export const memory = (files: Files, build: BuildInfo | null): Source => ({
  build: async () => build,
  async json<T>(file: string): Promise<T> {
    if (!Object.prototype.hasOwnProperty.call(files, file)) throw new Error(`data/${file}: not in the data the page sent`);
    const v = files[file];
    return (typeof v === 'string' ? JSON.parse(v) : v) as T;
  },
});

let source: Source = server;
export const setSource = (s: Source): void => { source = s; catalogueUrl = null; };

export const loadBuild = (): Promise<BuildInfo | null> => source.build();
export const isBroken = (b: BuildInfo | null): boolean => b?.status === 'broken';
/** A broken workspace without data (stage model or layout): there is nothing to draw. */
export const hasNoData = (b: BuildInfo | null): boolean => isBroken(b) && b?.stage !== 'check';
export const loadIndex = () => source.json<IndexJson>('index.json');
export const loadModel = (index: IndexJson) => source.json<ModelJson>(index.model.file);
export const loadScene = (index: IndexJson, key: string) => {
  const f = index.scenes[key];
  if (!f) return Promise.reject(new Error(`no scene ${key}`));
  return source.json<Scene>(f.file);
};

/** A workspace of the list `buildzr serve` makes (only what the switcher needs). */
export interface CatalogueItem { name: string; label: string; broken: boolean; href: string }

/** The other workspaces served next to this one, or [] when there is no list or it cannot be read. Never throws. */
export async function loadCatalogue(): Promise<CatalogueItem[]> {
  if (!catalogueUrl) return [];
  try {
    const r = await fetch(catalogueUrl);
    if (!r.ok) return [];
    const body = (await r.json()) as { workspaces?: unknown };
    if (!Array.isArray(body.workspaces)) return [];
    const root = new URL('../../', catalogueUrl); // the folder that holds every /<name>/, also behind a path prefix
    const items: CatalogueItem[] = [];
    for (const w of body.workspaces as Record<string, unknown>[]) {
      if (!w || typeof w.name !== 'string' || !w.viewerUrl) continue; // data only, no viewer: nothing to open
      const title = typeof w.workspaceName === 'string' && w.workspaceName ? w.workspaceName : w.name;
      items.push({ name: w.name, label: title, broken: w.status === 'broken', href: new URL(encodeURIComponent(w.name) + '/', root).href });
    }
    const count = (l: string): number => items.filter((i) => i.label === l).length;
    return items.map((i) => ({ ...i, label: (count(i.label) > 1 ? `${i.label} (${i.name})` : i.label) + (i.broken ? ' (broken)' : '') }));
  } catch {
    return [];
  }
}
