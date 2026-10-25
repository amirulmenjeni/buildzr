import { useEffect, useId, useRef, useState } from 'react';
import { download, ExportError, renderDiagram, type ExportFormat } from './export';
import { diagramRect, exportFilename } from './exportfile';
import { useDiagram } from './exportsource';
import { useStore } from './store';

/**
 * "Export" in the header: a button that opens a small menu to save the diagram on screen (the model canvas at its path, or the
 * authored view) as a PNG or an SVG file. It is outside the canvas, so it never covers the diagram and is never part of the
 * file. A failure is a notice; the viewer goes on.
 */
export function ExportMenu() {
  const model = useStore((s) => s.model);
  const view = useStore((s) => s.view);
  const path = useStore((s) => s.path);
  const theme = useStore((s) => s.theme);
  const composed = useDiagram((s) => s.composed);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [transparent, setTransparent] = useState(false);
  const running = useRef(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !toggle.current?.contains(t)) setOpen(false);
    };
    addEventListener('pointerdown', away);
    return () => removeEventListener('pointerdown', away);
  }, [open]);

  if (!model) return null;
  const close = (): void => { setOpen(false); toggle.current?.focus(); };

  const run = async (format: ExportFormat) => {
    if (running.current || !composed) return;
    running.current = true;
    setBusy(format);
    const filename = exportFilename(model.workspace.name, { view, path }, format);
    try {
      const viewport = document.querySelector<HTMLElement>('.react-flow__viewport');
      if (!viewport) throw new ExportError('The diagram is not on screen yet.');
      const m = useStore.getState().m;
      const what = view ? m?.viewByKey.get(view)?.title ?? view : path ? m?.byId.get(path)?.name ?? path : 'Landscape';
      const blob = await renderDiagram({ format, viewport, rect: diagramRect(composed), theme, transparent, title: `${model.workspace.name}: ${what}` });
      download(blob, filename);
      useStore.setState({ announce: `Downloaded ${filename}` });
    } catch (e) {
      const why = e instanceof Error ? e.message : String(e);
      useStore.setState({ notice: `Could not export ${filename}: ${why}` });
    } finally {
      running.current = false;
      setBusy(null);
    }
  };

  const off = !composed?.complete || busy !== null;
  return (
    <div className="export">
      <button ref={toggle} type="button" className="export-toggle" data-testid="export-toggle" aria-haspopup="true" aria-expanded={open} aria-controls={open ? menuId : undefined}
              onClick={() => (open ? close() : setOpen(true))}>
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
          <path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M12 4v11M7 10l5 5 5-5M5 20h14" />
        </svg>
        <span>Export</span>
      </button>
      {open && (
        <div ref={menu} id={menuId} className="export-menu" role="group" aria-label="Export the diagram" data-testid="export"
             onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); close(); } }}>
          <button type="button" data-format="png" disabled={off} aria-busy={busy === 'png'} onClick={() => void run('png')}>{busy === 'png' ? 'Exporting…' : 'Download PNG'}</button>
          <button type="button" data-format="svg" disabled={off} aria-busy={busy === 'svg'} onClick={() => void run('svg')}>{busy === 'svg' ? 'Exporting…' : 'Download SVG'}</button>
          <label>
            <input type="checkbox" checked={transparent} onChange={(e) => setTransparent(e.target.checked)} aria-describedby={`${menuId}-d`} /> Transparent background
          </label>
          <p id={`${menuId}-d`} className="export-note">The whole diagram, in the colours of the {theme} theme. Without a background it is only readable on a page of the same theme.</p>
        </div>
      )}
    </div>
  );
}
