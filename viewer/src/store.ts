import { create } from 'zustand';
import { loadIndex, loadModel, loadScene } from './data';
import { ancestors, chainOf, computeMatches, indexModel, typeLabel, type MatchInfo, type ModelIndex } from './model';
import { buildHash, emptyFilter, parseHash, type Filter, type Route } from './route';
import { loadSettings, saveSettings, type SettingId, type SettingValues } from './settings';
import type { IndexJson, ModelJson, Scene } from './types';

export interface CameraRequest { seq: number; kind: 'path' | 'node' | 'zoom'; id: string | null }

export interface State {
  status: 'loading' | 'ready' | 'error';
  error: string | null;
  index: IndexJson | null;
  model: ModelJson | null;
  m: ModelIndex | null;
  scenes: Record<string, Scene>;
  // ---- the four things the hash is derived from
  path: string; // deepest expanded element ('' = landscape); the chain is its ancestors + itself
  view: string | null; // authored view key, or null for the model canvas
  selection: string | null; // element id or scene edge id
  filter: Filter;
  // ---- UI state that is not in the hash
  notice: string | null;
  announce: string;
  treeOpen: Record<string, boolean>;
  rolled: boolean; // inspector: include descendants' relationships
  // phone layout (< 768 px): left drawer, bottom sheet, search row
  drawer: boolean;
  drawerTab: 'model' | 'views';
  sheet: 'peek' | 'half' | 'full';
  searchOpen: boolean;
  camera: CameraRequest;
  settings: SettingValues; // persisted in localStorage (settings.ts)
  // actions
  init(): Promise<void>;
  applyRoute(r: Route): void;
  expand(id: string): void;
  setPath(path: string): void;
  collapse(): void;
  zoomCollapse(to: string): void;
  openView(key: string, sel?: string | null): void;
  showInModel(): void;
  select(id: string | null, opts?: { reveal?: boolean; zoom?: boolean }): void;
  setFilter(f: Filter): void;
  gotoMatch(delta: 1 | -1): void;
  toggleTree(id: string, open?: boolean): void;
  setRolled(v: boolean): void;
  dismissNotice(): void;
  setSetting(id: SettingId, value: boolean): void;
  setUi(p: Partial<Pick<State, 'drawer' | 'drawerTab' | 'sheet' | 'searchOpen'>>): void;
}

const sceneKeysFor = (s: Pick<State, 'path' | 'view' | 'm'>): string[] => {
  if (!s.m) return [];
  if (s.view) {
    const v = s.m.viewByKey.get(s.view);
    return v ? [v.scene] : [];
  }
  return ['landscape', ...chainOf(s.m, s.path).map((id) => 'e/' + id)];
};

export const useStore = create<State>()((set, get) => {
  const loading = new Set<string>();

  /** Fetch every scene the current path/view needs and is missing. */
  const ensureScenes = (): void => {
    const s = get();
    if (!s.index) return;
    for (const key of sceneKeysFor(s)) {
      if (s.scenes[key] || loading.has(key)) continue;
      loading.add(key);
      loadScene(s.index, key)
        .then((sc) => set((cur) => ({ scenes: { ...cur.scenes, [key]: sc } })))
        .catch((e: unknown) => set({ status: 'error', error: String(e) }))
        .finally(() => loading.delete(key));
    }
  };

  const openAncestors = (ids: (string | null)[]): Record<string, boolean> => {
    const m = get().m!;
    const open = { ...get().treeOpen };
    for (const id of ids) if (id && m.byId.has(id)) for (const a of ancestors(m, id)) open[a] = true;
    return open;
  };

  const writeHash = (push: boolean): void => {
    const s = get();
    const h = buildHash({ view: s.view, path: s.path, sel: s.selection, filter: s.filter });
    if (h === location.hash) return;
    if (push) history.pushState(null, '', h);
    else history.replaceState(null, '', h);
  };

  const cam = (kind: 'path' | 'node' | 'zoom', id: string | null = null): CameraRequest => ({ seq: get().camera.seq + 1, kind, id });

  /** Apply a state change and its history entry in one step. */
  const commit = (patch: Partial<State>, push: boolean): void => {
    set(patch);
    writeHash(push);
    ensureScenes();
  };

  const announceExpand = (id: string): string => {
    const m = get().m!;
    const e = m.byId.get(id)!;
    const kids = e.children.length;
    const t = m.byId.get(e.children[0])?.type;
    return `Expanded ${e.name}, ${kids} ${t ? typeLabel(t).toLowerCase() : 'element'}${kids === 1 ? '' : 's'}`;
  };

  return {
    status: 'loading', error: null, index: null, model: null, m: null, scenes: {},
    path: '', view: null, selection: null, filter: emptyFilter,
    notice: null, announce: '', treeOpen: {}, rolled: false, drawer: false, drawerTab: 'model', sheet: 'peek', searchOpen: false, camera: { seq: 0, kind: 'path', id: null }, settings: loadSettings(),

    async init() {
      try {
        const index = await loadIndex();
        const model = await loadModel(index);
        const m = indexModel(model, index);
        set({ index, model, m, status: 'ready' });
        get().applyRoute(parseHash(location.hash));
        const fixed = buildHash({ view: get().view, path: get().path, sel: get().selection, filter: get().filter });
        if (fixed !== location.hash) history.replaceState(null, '', fixed);
      } catch (e) {
        set({ status: 'error', error: String(e) });
      }
    },

    /** Hash (load, back/forward, manual edit) -> state, with the fallbacks of docs/viewer-hash-routes.md. */
    applyRoute(r) {
      const m = get().m;
      if (!m) return;
      let notice: string | null = null;
      let view: string | null = null;
      let path = '';
      let sel: string | null = r.sel;
      if (r.view) {
        if (m.viewByKey.has(r.view)) view = r.view;
        else notice = `View ${r.view} not found; showing the model`;
      } else if (r.path) {
        let p = r.path;
        const el = m.byId.get(p);
        if (el && !m.expandable.has(p)) {
          // A leaf (or an element whose inside has no scene): expand to its parent and select it.
          sel = p;
          p = el.parent ?? '';
        } else {
          while (p && !m.expandable.has(p)) p = p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '';
          if (p !== r.path) notice = `${r.path} not found; showing ${p || 'the landscape'}`;
        }
        path = p;
      }
      if (sel && !m.byId.has(sel) && !sel.includes('->')) sel = null; // unknown or unsupported element: dropped silently
      const moved = get().camera.seq === 0 || view !== get().view || path !== get().path;
      set({ view, path, selection: sel, filter: r.filter, notice, ...(moved ? { camera: cam('path') } : {}) });
      const f = get().filter;
      const open = openAncestors([sel, path || null]);
      if (path) open[path] = true;
      const mi = computeMatches(m, f);
      if (mi) for (const id of mi.list) for (const a of ancestors(m, id)) open[a] = true;
      set({ treeOpen: open });
      ensureScenes();
    },

    expand(id) {
      const m = get().m!;
      if (!m.expandable.has(id)) { get().select(id, { reveal: true }); return; }
      commit({ view: null, path: id, selection: id, notice: null, camera: cam('path'), treeOpen: { ...openAncestors([id]), [id]: true }, announce: announceExpand(id) }, true);
    },

    setPath(path) {
      commit({ view: null, path, selection: path || null, notice: null, camera: cam('path'), treeOpen: openAncestors([path]),
        announce: path ? announceExpand(path) : 'Landscape' }, true);
    },

    collapse() {
      const { path, m } = get();
      if (!path || !m) return;
      const parent = m.byId.get(path)?.parent ?? '';
      commit({ path: parent, selection: path, notice: null, camera: cam('path'), announce: `Collapsed ${m.byId.get(path)!.name}` }, true);
    },

    /** Zooming out: collapse down to the ancestor `to` ('' = landscape). Same state change as `collapse`, applied once per call, but the camera stays where the user put it. */
    zoomCollapse(to) {
      const { path, m } = get();
      if (!path || !m) return;
      const chain = chainOf(m, path);
      const at = to ? chain.indexOf(to) : -1;
      if (to && at < 0) return;
      const gone = chain[at + 1]; // the highest frame that goes back to collapsed
      commit({ path: to, selection: gone, notice: null, announce: `Collapsed ${m.byId.get(gone)!.name}` }, true);
    },

    openView(key, sel = null) {
      const m = get().m!;
      if (!m.viewByKey.has(key)) return;
      commit({ view: key, selection: sel, notice: null, camera: cam('path'), treeOpen: openAncestors([sel]), announce: `Opened view ${m.viewByKey.get(key)!.title}` }, true);
    },

    showInModel() {
      const { selection, m } = get();
      const el = selection && m?.byId.get(selection);
      const path = el ? (el.parent ?? '') : '';
      commit({ view: null, path, notice: null, camera: cam('path'), treeOpen: openAncestors([selection]) }, true);
    },

    /** Select an element or edge. With `reveal` the canvas expands to the element's parent (tree, search results). */
    select(id, opts = {}) {
      const s = get();
      const m = s.m!;
      if (id === null) { commit({ selection: null }, false); return; }
      const el = m.byId.get(id);
      if (!el || !opts.reveal) {
        commit({ selection: id, camera: opts.zoom && el ? cam('zoom', id) : s.camera, treeOpen: openAncestors([el ? id : null]), sheet: 'peek' }, false);
        return;
      }
      let parent = el.parent ?? '';
      while (parent && !m.expandable.has(parent)) parent = m.byId.get(parent)?.parent ?? '';
      let view = s.view;
      let path = parent;
      if (view) {
        // Stay in the view when the element is drawn there; otherwise go to the model.
        const sc = s.scenes[m.viewByKey.get(view)?.scene ?? ''];
        if (sc && sc.nodes.some((n) => n.id === id)) path = s.path; else view = null;
      }
      const moved = view !== s.view || path !== s.path;
      commit({ view, path, selection: id, notice: null, treeOpen: openAncestors([id]),
        camera: moved ? cam('path') : cam('node', id), sheet: 'peek', drawer: false }, moved);
    },

    setFilter(f) {
      const m = get().m!;
      const open = { ...get().treeOpen };
      const mi: MatchInfo | null = computeMatches(m, f);
      if (mi) for (const id of mi.list) for (const a of ancestors(m, id)) open[a] = true;
      commit({ filter: f, treeOpen: open }, false);
    },

    gotoMatch(delta) {
      const s = get();
      const mi = computeMatches(s.m!, s.filter);
      if (!mi || mi.list.length === 0) return;
      const cur = s.selection ? mi.list.indexOf(s.selection) : -1;
      const n = mi.list.length;
      const next = cur < 0 ? (delta > 0 ? 0 : n - 1) : (cur + delta + n) % n;
      get().select(mi.list[next], { reveal: true });
    },

    toggleTree(id, open) {
      const t = get().treeOpen;
      set({ treeOpen: { ...t, [id]: open ?? !t[id] } });
    },
    setRolled(v) { set({ rolled: v }); },
    dismissNotice() { set({ notice: null }); },
    setSetting(id, value) {
      const settings = { ...get().settings, [id]: value };
      set({ settings });
      saveSettings(settings);
    },
    setUi(p) { set(p); },
  };
});

export function installRouter(): void {
  const onNav = (): void => {
    const s = useStore.getState();
    if (s.status !== 'ready') return;
    const r = parseHash(location.hash);
    const cur = buildHash({ view: s.view, path: s.path, sel: s.selection, filter: s.filter });
    if (buildHash(r) === cur && location.hash === cur) return;
    s.applyRoute(r);
    const st = useStore.getState();
    const fixed = buildHash({ view: st.view, path: st.path, sel: st.selection, filter: st.filter });
    if (fixed !== location.hash) history.replaceState(null, '', fixed);
  };
  addEventListener('popstate', onNav);
  addEventListener('hashchange', onNav);
}
