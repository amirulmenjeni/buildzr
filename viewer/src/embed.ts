// Embed mode (?embed=1). The message shapes and the origin rules are in protocol.ts; the reference for embedding pages
// is docs/ui-settings.md, "Embed the viewer".
import { parseMessage, trusted } from './protocol';
import { buildHash } from './route';
import { followHash, MODE, useStore } from './store';

const ORIGIN = location.origin;

const toParent = (msg: object): void => {
  if (window.parent !== window) window.parent.postMessage(msg, ORIGIN);
};
const ignored = (why: string, e: MessageEvent): void => console.debug(`buildzr viewer: message ignored (${why})`, e.origin);

/** Embed mode: listen to the parent page, report the route and the load status. */
export function installEmbed(): void {
  if (!MODE.embed) return;
  addEventListener('message', (e: MessageEvent) => {
    if (!trusted(e, window.parent === window ? null : window.parent, ORIGIN)) { ignored('not the parent page, or another origin', e); return; }
    const msg = parseMessage(e.data);
    if (!msg) { ignored('unknown message or wrong field types', e); return; }
    const st = useStore.getState();
    if (msg.type === 'buildzr:load') {
      if (MODE.data !== 'message') { ignored('data=server: the viewer reads data/', e); return; }
      if (msg.title) document.title = msg.title;
      void st.load(msg.files, msg.build, msg.route, msg.title);
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
    if (s.status === 'ready' && (s.view !== prev.view || s.path !== prev.path || s.selection !== prev.selection || s.filter !== prev.filter || prev.status !== 'ready')) {
      toParent({ type: 'buildzr:route', route: buildHash({ view: s.view, path: s.path, sel: s.selection, filter: s.filter }), view: s.view, path: s.path, selection: s.selection });
    }
  });
  toParent({ type: 'buildzr:ready', v: 1 });
}

