import { useEffect } from 'react';
import { BrokenBanner, BrokenScreen } from './Broken';
import { Canvas } from './Canvas';
import { Inspector } from './Inspector';
import { SettingsButton } from './SettingsPanel';
import { Breadcrumbs, Toolbar } from './Toolbar';
import { Tree, ViewsList } from './Tree';
import { installRouter, useStore } from './store';
import { usePhone } from './usePhone';
import oflUrl from './fonts/OFL.txt?url';

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
  const phone = usePhone();

  useEffect(() => { installRouter(); void useStore.getState().init(); }, []);
  useEffect(() => {
    if (!phone || !drawer) return;
    const f = (e: KeyboardEvent) => { if (e.key === 'Escape') setUi({ drawer: false }); };
    addEventListener('keydown', f);
    return () => removeEventListener('keydown', f);
  }, [phone, drawer, setUi]);

  if (status === 'broken' && build) return <BrokenScreen build={build} />;
  if (status === 'error') return <div role="alert" className="fatal">Could not load the model: {error}</div>;
  if (!m || !model) return <div className="fatal" role="status">Loading…</div>;

  const leftHidden = phone && !drawer;
  const sheetOpen = phone && selection !== null;
  return (
    <div className={'app' + (phone ? ' phone' : '')} data-phone={phone ? 'true' : undefined}>
      {build?.status === 'broken' && <BrokenBanner build={build} />}
      <header className="top">
        {phone && <button className="menu" aria-label="Open model navigation" aria-expanded={drawer} onClick={() => setUi({ drawer: true })}>☰</button>}
        <h1>{model.workspace.name}</h1>
        <Breadcrumbs />
        {phone && <button className="searchbtn" aria-label="Search and filter" aria-expanded={searchOpen} onClick={() => setUi({ searchOpen: !searchOpen })}>⌕</button>}
        {(!phone || searchOpen) && <Toolbar />}
      </header>
      {notice && <div role="status" className="notice" data-testid="notice">{notice} <button onClick={dismiss} aria-label="Dismiss">×</button></div>}
      {phone && drawer && <div className="backdrop" onClick={() => setUi({ drawer: false })} />}
      <nav className="left" aria-label="Model navigation" {...(leftHidden ? { inert: true, 'aria-hidden': true } : {})} data-open={phone && drawer ? 'true' : undefined}>
        {phone && (
          <div role="tablist" aria-label="Navigation" className="tabs">
            <button role="tab" aria-selected={drawerTab === 'model'} onClick={() => setUi({ drawerTab: 'model' })}>Model</button>
            <button role="tab" aria-selected={drawerTab === 'views'} onClick={() => setUi({ drawerTab: 'views' })}>Views</button>
          </div>
        )}
        {phone && <button className="close drawer-close" aria-label="Close navigation" onClick={() => setUi({ drawer: false })}>×</button>}
        {(!phone || drawerTab === 'model') && (<><h2 className="h">Model</h2><Tree /></>)}
        {(!phone || drawerTab === 'views') && (<><h2 className="h">Views</h2><ViewsList m={m} /></>)}
        <p className="legal"><a href={oflUrl} target="_blank" rel="noreferrer">Inter font licence (OFL-1.1)</a></p>
        <SettingsButton />
      </nav>
      <main className="center"><Canvas /></main>
      <div className={'sheet-wrap' + (phone ? ` sheet-${sheet}` : '')} data-sheet={phone ? (sheetOpen ? sheet : 'closed') : undefined} {...(phone && !sheetOpen ? { inert: true, 'aria-hidden': true } : {})}>
        {phone && (
          <div className="sheet-bar">
            <button aria-label={sheet === 'full' ? 'Shrink inspector' : 'Grow inspector'} onClick={() => setUi({ sheet: sheet === 'peek' ? 'half' : sheet === 'half' ? 'full' : 'peek' })}><span className="grip" /></button>
            <button className="close" aria-label="Close inspector" onClick={() => select(null)}>×</button>
          </div>
        )}
        <Inspector />
      </div>
      <div className="sr-only" aria-live="polite" data-testid="live">{announce}</div>
    </div>
  );
}
