import { useEffect } from 'react';
import { BrokenBanner, BrokenScreen } from './Broken';
import { AboutButton } from './About';
import { Canvas } from './Canvas';
import { ExportMenu } from './ExportMenu';
import { Inspector } from './Inspector';
import { Playback } from './Playback';
import { SettingsButton } from './SettingsPanel';
import { Breadcrumbs, Toolbar } from './Toolbar';
import { Tree, ViewsList } from './Tree';
import { WorkspaceSwitcher } from './Workspaces';
import { canOpenInNewTab, installEmbed, openInNewTab } from './embed';
import { installRouter, MODE, useStore } from './store';
import { usePhone } from './usePhone';

export function App() {
  const status = useStore((s) => s.status);
  const error = useStore((s) => s.error);
  const build = useStore((s) => s.build);
  const m = useStore((s) => s.m);
  const model = useStore((s) => s.model);
  const notice = useStore((s) => s.notice);
  const announce = useStore((s) => s.announce);
  const dismiss = useStore((s) => s.dismissNotice);
  const drawer = useStore((s) => s.drawer);
  const drawerTab = useStore((s) => s.drawerTab);
  const sheet = useStore((s) => s.sheet);
  const searchOpen = useStore((s) => s.searchOpen);
  const selection = useStore((s) => s.selection);
  const setUi = useStore((s) => s.setUi);
  const select = useStore((s) => s.select);
  const inspectorOpen = useStore((s) => s.inspectorOpen);
  const closeInspector = useStore((s) => s.closeInspector);
  const phone = usePhone();
  const embed = MODE.embed;
  const drawerMode = phone || embed; // the left panel is a drawer on a phone and in an embedded frame of any width

  useEffect(() => {
    installRouter();
    installEmbed();
    if ((!embed || MODE.data === 'server') && !MODE.handoff) void useStore.getState().init();
  }, [embed]);
  useEffect(() => {
    if (!drawerMode || !drawer) return;
    const f = (e: KeyboardEvent) => { if (e.key === 'Escape') setUi({ drawer: false }); };
    addEventListener('keydown', f);
    return () => removeEventListener('keydown', f);
  }, [drawerMode, drawer, setUi]);
  useEffect(() => {
    if (!embed || !inspectorOpen || drawer) return;
    const f = (e: KeyboardEvent) => { if (e.key === 'Escape') closeInspector(); };
    addEventListener('keydown', f);
    return () => removeEventListener('keydown', f);
  }, [embed, inspectorOpen, drawer, closeInspector]);

  if (status === 'gone') return (
    <div role="alert" className="fatal gone" data-testid="handoff-gone">
      <h1>This diagram is no longer available</h1>
      <p>The page that opened this model was closed or reloaded, so its diagram is no longer available. Go back to that page and press Open in a new tab again.</p>
    </div>
  );
  if (status === 'broken' && build) return <BrokenScreen build={build} />;
  if (status === 'error') return <div role="alert" className="fatal">Could not load the model: {error}<WorkspaceSwitcher /></div>;
  if (!m || !model) return <div className="fatal" role="status">Loading…</div>;

  const leftHidden = drawerMode && !drawer;
  const sheetOpen = phone && selection !== null && (!embed || inspectorOpen);
  const sideOpen = !phone && (!embed || inspectorOpen); // the inspector column (wide layouts)
  const cls = ['app', phone ? 'phone' : '', embed ? 'embed' : '', embed && sideOpen ? 'insp-open' : ''].filter(Boolean).join(' ');
  return (
    <div className={cls} data-phone={phone ? 'true' : undefined} data-embed={embed ? 'true' : undefined}>
      {build?.status === 'broken' && <BrokenBanner build={build} />}
      <header className="top">
        {drawerMode && <button className="menu" aria-label="Open model navigation" aria-expanded={drawer} onClick={() => setUi({ drawer: true })}>☰</button>}
        <h1>{model.workspace.name}</h1>
        <Breadcrumbs />
        <ExportMenu />
        {drawerMode && <button className="searchbtn" aria-label="Search and filter" aria-expanded={searchOpen} onClick={() => setUi({ searchOpen: !searchOpen })}>⌕</button>}
        {embed && canOpenInNewTab() && (
          <button className="newtab" data-testid="open-new-tab" title="Open this diagram in the full viewer, in a new browser tab" onClick={openInNewTab}>
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
              <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" />
            </svg>
            <span className="newtab-text">Open in a new tab</span>
          </button>
        )}
        {(!drawerMode || searchOpen) && <Toolbar />}
      </header>
      {notice && <div role="status" className="notice" data-testid="notice">{notice} <button onClick={dismiss} aria-label="Dismiss">×</button></div>}
      {drawerMode && drawer && <div className="backdrop" onClick={() => setUi({ drawer: false })} />}
      <nav className="left" aria-label="Model navigation" {...(leftHidden ? { inert: true, 'aria-hidden': true } : {})} data-open={drawerMode && drawer ? 'true' : undefined}>
        {drawerMode && (
          <div role="tablist" aria-label="Navigation" className="tabs">
            <button role="tab" aria-selected={drawerTab === 'model'} onClick={() => setUi({ drawerTab: 'model' })}>Model</button>
            <button role="tab" aria-selected={drawerTab === 'views'} onClick={() => setUi({ drawerTab: 'views' })}>Views</button>
          </div>
        )}
        {drawerMode && <button className="close drawer-close" aria-label="Close navigation" onClick={() => setUi({ drawer: false })}>×</button>}
        <WorkspaceSwitcher />
        {(!drawerMode || drawerTab === 'model') && (<><h2 className="h">Model</h2><Tree /></>)}
        {(!drawerMode || drawerTab === 'views') && (<><h2 className="h">Views</h2><ViewsList m={m} /></>)}
        <SettingsButton extra={<AboutButton />} />
      </nav>
      <main className="center"><Canvas /><Playback /></main>
      {(phone || sideOpen) && (
      <div className={'sheet-wrap' + (phone ? ` sheet-${sheet}` : '')} data-sheet={phone ? (sheetOpen ? sheet : 'closed') : undefined} {...(phone && !sheetOpen ? { inert: true, 'aria-hidden': true } : {})}>
        {phone && (
          <div className="sheet-bar">
            <button aria-label={sheet === 'full' ? 'Shrink inspector' : 'Grow inspector'} onClick={() => setUi({ sheet: sheet === 'peek' ? 'half' : sheet === 'half' ? 'full' : 'peek' })}><span className="grip" /></button>
            <button className="close" aria-label="Close inspector" onClick={() => select(null)}>×</button>
          </div>
        )}
        {embed && !phone && <button className="close inspector-close" aria-label="Close inspector" onClick={closeInspector}>×</button>}
        <Inspector />
      </div>
      )}
      <div className="sr-only" aria-live="polite" data-testid="live">{announce}</div>
    </div>
  );
}
