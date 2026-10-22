// Embed mode (?embed=1) and the new tab it can open (?handoff=<id>). The message shapes and the origin rules are
// in protocol.ts; the reference for embedding pages is docs/ui-settings.md, "Embed the viewer".
import { newId, parseMessage, trusted, type Files, type WorkspaceSet } from './protocol';
import { buildHash } from './route';
import { followHash, MODE, useStore } from './store';
import type { BuildInfo } from './types';

const ORIGIN = location.origin;
const WAIT_MS = 5000; // how long a new tab asks its opener for the data
const ASK_EVERY_MS = 250;
const STORE_PREFIX = 'buildzr-ui:handoff:';

interface Loaded { id: string; files: Files; build: BuildInfo | null; title: string | null; group: WorkspaceSet | null }
let current: Loaded | null = null; // the data this frame was given last, under the id a new tab asks for
const opened = new Set<MessageEventSource>(); // the tabs this frame opened: the only windows it answers

const toParent = (msg: object): void => {
  if (window.parent !== window) window.parent.postMessage(msg, ORIGIN);
};
const ignored = (why: string, e: MessageEvent): void => console.debug(`buildzr viewer: message ignored (${why})`, e.origin);

/** Embed mode: listen to the parent page, answer the tabs this frame opened, report the route and the load status. */
export function installEmbed(): void {
  if (!MODE.embed) {
    if (MODE.handoff) void receiveHandoff(MODE.handoff);
    return;
  }
  addEventListener('message', (e: MessageEvent) => {
    if (opened.has(e.source as MessageEventSource)) { answerTab(e); return; }
    if (!trusted(e, window.parent === window ? null : window.parent, ORIGIN)) { ignored('not the parent page, or another origin', e); return; }
    const msg = parseMessage(e.data);
    if (!msg) { ignored('unknown message or wrong field types', e); return; }
    const st = useStore.getState();
    if (msg.type === 'buildzr:load') {
      if (MODE.data !== 'message') { ignored('data=server: the viewer reads data/', e); return; }
      current = { id: newId(), files: msg.files, build: msg.build, title: msg.title, group: msg.group };
      if (msg.title) document.title = msg.title;
      void st.load(msg.files, msg.build, msg.route, msg.title, msg.group);
    } else if (msg.type === 'buildzr:theme') {
      st.setThemeOverride(msg.theme);
    } else if (msg.type === 'buildzr:route') {
      if (st.status !== 'ready') return;
      history.replaceState(null, '', msg.route || '#/m');
      followHash();
    }
  });
  useStore.subscribe((s, prev) => {
    if (s.status !== prev.status && (s.status === 'ready' || s.status === 'broken' || s.status === 'error')) {
      toParent({ type: 'buildzr:loaded', status: s.status, ...(s.error ? { error: s.error } : {}) });
    }
    if (s.activeWorkspace !== prev.activeWorkspace && s.activeWorkspace) toParent({ type: 'buildzr:workspace', name: s.activeWorkspace });
    if (s.status === 'ready' && (s.view !== prev.view || s.path !== prev.path || s.selection !== prev.selection || s.filter !== prev.filter || prev.status !== 'ready')) {
      toParent({ type: 'buildzr:route', route: buildHash({ view: s.view, path: s.path, sel: s.selection, filter: s.filter }), view: s.view, path: s.path, selection: s.selection });
    }
  });
  toParent({ type: 'buildzr:ready', v: 1 });
}

/** True when "Open in a new tab" can do something: data from the server, or data the parent page sent. */
export const canOpenInNewTab = (): boolean => MODE.embed && (MODE.data === 'server' || current !== null);

/** "Open in a new tab": the full viewer on the same model and route. */
export function openInNewTab(): void {
  const url = new URL(location.href);
  url.hash = location.hash;
  if (MODE.data === 'server') {
    url.search = '';
    window.open(url.href, '_blank', 'noopener');
  } else {
    if (!current) return;
    url.search = '?handoff=' + current.id;
    const w = window.open(url.href, '_blank'); // not noopener: the new tab asks this frame (its opener) for the data
    if (w) opened.add(w);
  }
  toParent({ type: 'buildzr:open', url: url.href });
}

/** The data for a new tab: the workspace on screen, and the others of the same load, so the tab keeps the switcher. */
function handoffMessage(c: Loaded): object {
  const active = useStore.getState().activeWorkspace;
  const base = { type: 'buildzr:handoff', id: c.id, title: c.title };
  if (!c.group) return { ...base, files: c.files, build: c.build };
  return { ...base, workspaces: c.group.workspaces, active: c.group.workspaces.some((w) => w.name === active) ? active : c.group.active };
}

/** A tab this frame opened asks for the data. */
function answerTab(e: MessageEvent): void {
  if (e.origin !== ORIGIN) { ignored('another origin', e); return; }
  const msg = parseMessage(e.data);
  if (!msg || msg.type !== 'buildzr:handoff-request') { ignored('not a handoff request', e); return; }
  const to = e.source as Window;
  if (current && msg.id === current.id) {
    to.postMessage(handoffMessage(current), ORIGIN);
  } else {
    to.postMessage({ type: 'buildzr:handoff-missing', id: msg.id }, ORIGIN);
  }
}

/** The new tab: the data from this tab's own storage (a reload), else from the frame that opened it. */
async function receiveHandoff(id: string): Promise<void> {
  const key = STORE_PREFIX + id;
  const st = useStore.getState();
  const use = (m: { files: Files; build: BuildInfo | null; title: string | null; group: WorkspaceSet | null }): void => {
    if (m.title) document.title = m.title;
    void st.load(m.files, m.build, null, m.title, m.group);
  };
  try {
    const saved = sessionStorage.getItem(key);
    const msg = saved ? parseMessage(JSON.parse(saved)) : null;
    if (msg?.type === 'buildzr:handoff' && msg.id === id) { use(msg); return; }
  } catch { /* blocked or corrupted storage: ask the opener */ }
  const opener = window.opener as Window | null;
  if (!opener || opener.closed) { st.setGone(); return; }
  await new Promise<void>((done) => {
    let timer = 0;
    const finish = (): void => { clearInterval(timer); clearTimeout(stop); removeEventListener('message', on); done(); };
    const on = (e: MessageEvent): void => {
      if (!trusted(e, opener, ORIGIN)) return;
      const msg = parseMessage(e.data);
      if (!msg || !('id' in msg) || msg.id !== id) return;
      if (msg.type === 'buildzr:handoff') {
        try { sessionStorage.setItem(key, JSON.stringify(e.data)); } catch { /* too big, or blocked: a reload asks the opener again */ }
        use(msg);
        finish();
      } else if (msg.type === 'buildzr:handoff-missing') {
        st.setGone();
        finish();
      }
    };
    addEventListener('message', on);
    const ask = (): void => { try { opener.postMessage({ type: 'buildzr:handoff-request', id }, ORIGIN); } catch { /* opener gone */ } };
    ask();
    timer = window.setInterval(ask, ASK_EVERY_MS);
    const stop = window.setTimeout(() => { st.setGone(); finish(); }, WAIT_MS);
  });
}
