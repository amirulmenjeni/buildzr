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
const server: Source = {
  /** build.json, or null when it cannot be read (an old build, or a host that does not serve it): then all is ok. */
  async build() {
    try {
      const r = await fetch('build.json');
      if (!r.ok) return null;
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
export const setSource = (s: Source): void => { source = s; };

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
