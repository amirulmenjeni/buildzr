import { create } from 'zustand';
import { applyFamily, fontsReady } from './branding';
import { hasNoData, loadBranding, loadBuild, loadCatalogue, loadIndex, loadModel, loadScene, memory, setSource } from './data';
import { parseMode, type Files, type ThemeChoice, type WorkspaceSet } from './protocol';
import { ancestors, chainOf, computeMatches, indexModel, isCustom, isDeployment, isViewOnly, typeLabel, type MatchInfo, type ModelIndex } from './model';
import { buildHash, emptyFilter, parseHash, type Filter, type Route } from './route';
import { loadSettings, saveSettings, type SettingId, type SettingValue, type SettingValues } from './settings';
import { resolveTheme, type Theme } from './theme';
import type { BrandingJson, BuildInfo, IndexJson, ModelJson, Scene } from './types';

/** How this page was opened (the search part of the URL): standalone, embedded in a frame, or a new tab handed data. */
export const MODE = parseMode(location.search);
const DARK = '(prefers-color-scheme: dark)';
const prefersDark = (): boolean => typeof matchMedia === 'function' && matchMedia(DARK).matches;

/** One entry of the workspace switcher: `href` when it is another page (a served catalogue), else the data is in memory. */
export interface WorkspaceChoice { id: string; label: string; href: string | null }

export interface CameraRequest { seq: number; kind: 'path' | 'node' | 'zoom'; id: string | null }

export interface State {
  status: 'loading' | 'ready' | 'error' | 'broken' | 'gone'; // broken: build.json says so and there is no data to draw; gone: a new tab whose data is no longer available
  error: string | null;
  build: BuildInfo | null; // build.json, read first
  index: IndexJson | null;
  model: ModelJson | null;
  m: ModelIndex | null;
  scenes: Record<string, Scene>;
  branding: BrandingJson | null; // icons, logo and diagram font; null for a workspace without them
  fontEpoch: number; // bumped when a font face finishes loading while a branding font is set: labels fit themselves again
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
  themeOverride: ThemeChoice | null; // embed: the theme the parent page asked for (not stored)
  theme: Theme; // resolved: override, else the setting; 'system' follows prefers-color-scheme
  inspectorOpen: boolean; // embed: the inspector shows only after an explicit selection
  title: string | null; // embed / new tab: the title the parent page gave
  workspaces: WorkspaceChoice[]; // the switcher lists these; it shows only when there are two or more
  activeWorkspace: string | null; // the id of the one on screen
  step: number; // a dynamic view stepped through: the step on screen (1-based); 0 = the whole diagram, as drawn
  playing: boolean; // the steps advance by themselves (Playback.tsx)
  // actions
  init(): Promise<void>;
  applyRoute(r: Route): void;
  expand(id: string): void;
  setPath(path: string): void;
  collapse(): void;
  zoomCollapse(to: string): void;
  zoomExpand(id: string): void;
  prefetch(id: string): void;
  openView(key: string, sel?: string | null): void;
  showInModel(): void;
  showInstance(id: string): void;
  select(id: string | null, opts?: { reveal?: boolean; zoom?: boolean }): void;
  setFilter(f: Filter): void;
  gotoMatch(delta: 1 | -1): void;
  toggleTree(id: string, open?: boolean): void;
  setRolled(v: boolean): void;
  dismissNotice(): void;
  setSetting(id: SettingId, value: SettingValue): void;
  setThemeOverride(t: ThemeChoice | null): void;
  syncTheme(): void;
  closeInspector(): void;
  load(files: Files, build: BuildInfo | null, route: string | null, title: string | null, group?: WorkspaceSet | null): Promise<void>;
  switchWorkspace(id: string): void;
  setGone(): void;
  setUi(p: Partial<Pick<State, 'drawer' | 'drawerTab' | 'sheet' | 'searchOpen'>>): void;
  setStep(step: number, announce: string, playing?: boolean): void;
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

  /** The workspaces served next to this one (buildzr serve), for the switcher. The page does not wait for them. */
  const listWorkspaces = async (gen: number, build: BuildInfo | null): Promise<void> => {
    if (memorySet) return;
    const catalogue = await loadCatalogue();
    const here = build?.name ?? null;
    if (gen !== generation || !here || catalogue.length < 2 || !catalogue.some((c) => c.name === here)) return;
    set({ workspaces: catalogue.map((c) => ({ id: c.name, label: c.label, href: c.href })), activeWorkspace: here });
  };

  /** Fetch every scene the current path/view needs and is missing. */
  const ensureScenes = (): void => {
    const s = get();
    if (!s.index) return;
    for (const key of sceneKeysFor(s)) {
      if (s.scenes[key] || loading.has(key)) continue;
      loading.add(key);
      const gen = generation;
      loadScene(s.index, key)
        .then((sc) => { if (gen === generation) set((cur) => ({ scenes: { ...cur.scenes, [key]: sc } })); })
        .catch((e: unknown) => { if (gen === generation) set({ status: 'error', error: String(e) }); })
        .finally(() => loading.delete(key));
    }
  };

  /** Fetch the scene of a frame ahead of its expansion. A failure is silent: the expansion itself reports it. */
  const prefetchScene = (key: string): void => {
    const s = get();
    if (!s.index || s.scenes[key] || loading.has(key) || !(key in s.index.scenes)) return;
    loading.add(key);
    const gen = generation;
    loadScene(s.index, key)
      .then((sc) => { if (gen === generation) set((cur) => ({ scenes: { ...cur.scenes, [key]: sc } })); })
      .catch(() => undefined)
      .finally(() => loading.delete(key));
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
    if (push && !MODE.embed) history.pushState(null, '', h); // embedded: never step the parent page's history
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

  let memorySet: WorkspaceSet | null = null; // the workspaces an embedding page sent in one load
  let generation = 0; // bumped by every load: scenes of an older model are dropped when they arrive
  const initial = loadSettings();

  return {
    status: 'loading', error: null, build: null, index: null, model: null, m: null, scenes: {}, branding: null, fontEpoch: 0,
    path: '', view: null, selection: null, filter: emptyFilter,
    notice: null, announce: '', treeOpen: {}, rolled: false, drawer: false, drawerTab: 'model', sheet: 'peek', searchOpen: false, camera: { seq: 0, kind: 'path', id: null }, settings: initial,
    themeOverride: MODE.theme, theme: resolveTheme(MODE.theme ?? initial.theme, prefersDark()), inspectorOpen: false, title: null,
    workspaces: [], activeWorkspace: null, step: 0, playing: false,

    async init() {
      const gen = generation;
      try {
        const build = await loadBuild();
        if (gen !== generation) return;
        set({ build });
        void listWorkspaces(gen, build);
        if (hasNoData(build)) { set({ status: 'broken' }); return; }
        const index = await loadIndex();
        const model = await loadModel(index);
        const branding = await loadBranding(index);
        const family = branding?.font?.family ?? null;
        applyFamily(family);
        // the labels are drawn once the branding font is there (or the wait is over), so the first drawing is in it
        if (family && !(await fontsReady(family))) console.warn(`buildzr: the branding font (${family}) did not load in time; the labels fit themselves to it when it does`);
        if (gen !== generation) return;
        const m = indexModel(model, index);
        set({ index, model, m, branding, status: 'ready' });
        get().applyRoute(parseHash(location.hash));
        const fixed = buildHash({ view: get().view, path: get().path, sel: get().selection, filter: get().filter });
        if (fixed !== location.hash) history.replaceState(null, '', fixed);
      } catch (e) {
        if (gen === generation) set({ status: 'error', error: String(e) });
      }
    },

    /** Data from an embedding page or an opener (embed.ts): replaces the model and starts again from the route. */
    async load(files, build, route, title, group = null) {
      generation++;
      loading.clear();
      setSource(memory(files, build));
      memorySet = group;
      if (route !== null) history.replaceState(null, '', route || '#/m');
      set({ status: 'loading', error: null, build: null, index: null, model: null, m: null, scenes: {}, branding: null, path: '', view: null, selection: null,
        filter: emptyFilter, notice: null, treeOpen: {}, drawer: false, sheet: 'peek', searchOpen: false, inspectorOpen: false, title,
        workspaces: group ? group.workspaces.map((w) => ({ id: w.name, label: w.name, href: null })) : [], activeWorkspace: group?.active ?? null });
      await get().init();
    },
    /** The reader picked a workspace: another page (a served catalogue), or other data the embedding page sent. */
    switchWorkspace(id) {
      const to = get().workspaces.find((w) => w.id === id);
      if (!to || id === get().activeWorkspace) return;
      if (to.href) {
        const url = new URL(to.href);
        if (MODE.embed) url.search = location.search; // the frame stays an embed of the same kind
        location.assign(url.href);
        return;
      }
      const w = memorySet?.workspaces.find((x) => x.name === id);
      if (!w || !memorySet) return;
      void get().load(w.files, w.build, w.route ?? '', get().title, { workspaces: memorySet.workspaces, active: id })
        .then(() => set({ announce: `Opened workspace ${id}` }));
    },
    setGone() { generation++; set({ status: 'gone' }); },

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
      } else if (r.path && isViewOnly(m.byId.get(r.path))) {
        // Deployment and custom elements are drawn in views only: open the first one that shows it.
        const el = m.byId.get(r.path)!;
        if (el.views.length && m.viewByKey.has(el.views[0])) { view = el.views[0]; sel = el.id; }
        else notice = `${r.path} is in no ${isCustom(el) ? '' : 'deployment '}view; showing the landscape`;
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

    /** Zooming in: expand `id`. The same state change as a click (`expand`: one history entry, hash, tree, selection, announcement), but the camera stays where the user put it. */
    zoomExpand(id) {
      const m = get().m!;
      if (!m.expandable.has(id)) return;
      commit({ view: null, path: id, selection: id, notice: null, treeOpen: { ...openAncestors([id]), [id]: true }, announce: announceExpand(id) }, true);
    },

    prefetch(id) { prefetchScene('e/' + id); },

    openView(key, sel = null) {
      const m = get().m!;
      if (!m.viewByKey.has(key)) return;
      commit({ view: key, selection: sel, notice: null, camera: cam('path'), treeOpen: openAncestors([sel]), announce: `Opened view ${m.viewByKey.get(key)!.title}` }, true);
    },

    showInModel() {
      const { m } = get();
      let selection = get().selection;
      const inst = selection ? m?.byId.get(selection) : undefined;
      if (isCustom(inst)) return; // a custom element has no place in the model: there is nothing to show it in
      if (inst && isDeployment(inst)) selection = inst.instanceOf ?? null; // an instance: show its container or system
      const el = selection && m?.byId.get(selection);
      const path = el ? (el.parent ?? '') : '';
      commit({ view: null, path, selection, notice: null, camera: cam('path'), treeOpen: openAncestors([selection]) }, true);
    },

    /** From a software system or container to one of the deployment instances that run it: opens a deployment view that draws the instance (the current one when it does) and selects it. */
    showInstance(id) {
      const m = get().m!;
      const inst = m.byId.get(id);
      if (!inst || !isDeployment(inst) || !inst.views.some((k) => m.viewByKey.has(k))) return; // drawn nowhere: nothing to show
      get().select(id, { reveal: true });
      const v = get().view;
      set({ announce: `Showing ${inst.name} in ${v ? m.viewByKey.get(v)?.title ?? v : 'its deployment view'}` });
      requestAnimationFrame(() => document.querySelector<HTMLElement>('.inspector h2')?.focus()); // the button that was clicked is gone
    },

    /** Select an element or edge. With `reveal` the canvas expands to the element's parent (tree, search results). */
    select(id, opts = {}) {
      const s = get();
      const m = s.m!;
      if (id === null) { commit({ selection: null, inspectorOpen: false }, false); return; }
      set({ inspectorOpen: true }); // an explicit selection: the embed shows the inspector
      const el = m.byId.get(id);
      if (!el || !opts.reveal) {
        commit({ selection: id, camera: opts.zoom && el ? cam('zoom', id) : s.camera, treeOpen: openAncestors([el ? id : null]), sheet: 'peek' }, false);
        return;
      }
      if (isViewOnly(el)) {
        // Drawn in views only (deployment and custom elements): stay in the current view when it shows the element, else open the first that does.
        const here = s.view ? s.scenes[m.viewByKey.get(s.view)?.scene ?? ''] : undefined;
        const view = here?.nodes.some((n) => n.id === id) ? s.view : el.views.find((k) => m.viewByKey.has(k)) ?? s.view;
        const moved = view !== s.view;
        commit({ view, selection: id, notice: null, treeOpen: openAncestors([id]),
          camera: moved ? cam('path') : cam('node', id), sheet: 'peek', drawer: false }, moved);
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
      set({ settings, ...(id === 'theme' ? { themeOverride: null } : {}) }); // the reader's own choice wins over the page's
      saveSettings(settings);
      get().syncTheme();
    },
    setThemeOverride(t) { set({ themeOverride: t }); get().syncTheme(); },
    syncTheme() {
      const s = get();
      const theme = resolveTheme(s.themeOverride ?? s.settings.theme, prefersDark());
      if (theme !== s.theme) set({ theme });
    },
    closeInspector() { commit({ selection: null, inspectorOpen: false }, false); },
    setUi(p) { set(p); },
    /** Back to step 0 (the whole diagram): the camera goes back to the default fit, the steps may have moved it (Canvas: StepCamera). */
    setStep(step, announce, playing = false) { set({ step, playing, announce, ...(step === 0 && get().step > 0 ? { camera: cam('path') } : {}) }); },
  };
});

// Stepping is a way of looking at one view: another view, another selection or another model shows the whole diagram again,
// at the default fit unless that change already moves the camera.
useStore.subscribe((s, prev) => {
  if ((s.step !== 0 || s.playing) && (s.view !== prev.view || s.selection !== prev.selection || s.m !== prev.m)) {
    const fit = s.step !== 0 && s.camera.seq === prev.camera.seq;
    useStore.setState({ step: 0, playing: false, ...(fit ? { camera: { seq: s.camera.seq + 1, kind: 'path', id: null } } : {}) });
  }
});

/** Keep <html data-theme> on the resolved theme, and follow the device's light/dark setting. */
export function installTheme(): void {
  const apply = (t: Theme): void => {
    document.documentElement.dataset.theme = t;
    document.documentElement.style.colorScheme = t;
  };
  apply(useStore.getState().theme);
  useStore.subscribe((s, prev) => { if (s.theme !== prev.theme) apply(s.theme); });
  if (typeof matchMedia === 'function') matchMedia(DARK).addEventListener('change', () => useStore.getState().syncTheme());
}

/** location.hash -> state (back/forward, a manual edit, an embedding page's route message). */
export function followHash(): void {
  const s = useStore.getState();
  if (s.status !== 'ready') return;
  const r = parseHash(location.hash);
  const cur = buildHash({ view: s.view, path: s.path, sel: s.selection, filter: s.filter });
  if (buildHash(r) === cur && location.hash === cur) return;
  s.applyRoute(r);
  const st = useStore.getState();
  const fixed = buildHash({ view: st.view, path: st.path, sel: st.selection, filter: st.filter });
  if (fixed !== location.hash) history.replaceState(null, '', fixed);
}

export function installRouter(): void {
  addEventListener('popstate', followHash);
  addEventListener('hashchange', followHash);
}

if (typeof document !== 'undefined' && document.fonts) {
  document.fonts.addEventListener?.('loadingdone', () => {
    if (useStore.getState().branding?.font) useStore.setState((s) => ({ fontEpoch: s.fontEpoch + 1 }));
  });
}
