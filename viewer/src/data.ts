import type { IndexJson, ModelJson, Scene } from './types';

// All URLs are relative to index.html so the site works at / and at a subpath, offline.
const get = async <T,>(url: string): Promise<T> => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return (await r.json()) as T;
};
export const loadIndex = () => get<IndexJson>('data/index.json');
export const loadModel = (index: IndexJson) => get<ModelJson>('data/' + index.model.file);
export const loadScene = (index: IndexJson, key: string) => {
  const f = index.scenes[key];
  if (!f) return Promise.reject(new Error(`no scene ${key}`));
  return get<Scene>('data/' + f.file);
};
