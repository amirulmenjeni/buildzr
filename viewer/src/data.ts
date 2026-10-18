import type { BuildInfo, IndexJson, ModelJson, Scene } from './types';

// All URLs are relative to index.html so the site works at / and at a subpath, offline.
const get = async <T,>(url: string): Promise<T> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return (await r.json()) as T;
};
/** build.json, or null when it cannot be read (an old build, or a host that does not serve it): then all is ok. */
export const loadBuild = async (): Promise<BuildInfo | null> => {
  try {
    const r = await fetch('build.json');
    if (!r.ok) return null;
    const b = (await r.json()) as unknown;
    return b && typeof b === 'object' && !Array.isArray(b) ? (b as BuildInfo) : null;
  } catch {
    return null;
  }
};
export const isBroken = (b: BuildInfo | null): boolean => b?.status === 'broken';
/** A broken workspace without data (stage model or layout): there is nothing to draw. */
export const hasNoData = (b: BuildInfo | null): boolean => isBroken(b) && b?.stage !== 'check';
export const loadIndex = () => get<IndexJson>('data/index.json');
export const loadModel = (index: IndexJson) => get<ModelJson>('data/' + index.model.file);
export const loadScene = (index: IndexJson, key: string) => {
  const f = index.scenes[key];
  if (!f) return Promise.reject(new Error(`no scene ${key}`));
  return get<Scene>('data/' + f.file);
};
