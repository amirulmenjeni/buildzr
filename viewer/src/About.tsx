import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import noticesUrl from '../../THIRD_PARTY_NOTICES.txt?url';

const FOCUSABLE = 'a[href], button, [tabindex]:not([tabindex="-1"])';

/** The About button (bottom-left of the left panel) and its dialog: what the viewer is, the bundled font, and
 * the third-party notices, read from a file next to the page (no network beyond the page's own origin). */
export function AboutButton() {
  const [open, setOpen] = useState(false);
  const [notices, setNotices] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const title = useId();

  useEffect(() => {
    if (!open) return;
    dialog.current?.querySelector<HTMLElement>('.about-close')?.focus();
    if (notices !== null || failed) return;
    const ctl = new AbortController();
    fetch(noticesUrl, { signal: ctl.signal })
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then(setNotices)
      .catch(() => { if (!ctl.signal.aborted) setFailed(true); });
    return () => ctl.abort();
  }, [open, notices, failed]);

  const close = (): void => { setOpen(false); button.current?.focus(); };
  const onKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === 'Escape') { e.stopPropagation(); close(); return; }
    if (e.key !== 'Tab') return;
    // Keep Tab inside the dialog: it is modal.
    const items = [...(dialog.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];
    if (!items.length) return;
    const first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  return (
    <>
      <button ref={button} className="about-btn" aria-haspopup="dialog" aria-expanded={open} data-testid="about-button" onClick={() => setOpen(true)}>
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
          <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" d="M12 11v5.5M12 7.6v.1" />
        </svg>
        About
      </button>
      {open && createPortal(
        <div className="about-backdrop" onPointerDown={(e) => { if (e.target === e.currentTarget) close(); }}>
          <div ref={dialog} className="about" role="dialog" aria-modal="true" aria-labelledby={title} data-testid="about-dialog" onKeyDown={onKeyDown}>
            <div className="about-head">
              <h2 id={title}>About the buildzr viewer</h2>
              <button className="about-close" aria-label="Close About" onClick={close}>×</button>
            </div>
            <div className="about-body">
              <p>The buildzr viewer is a read-only browser for a Structurizr-style C4 model. It runs entirely from this page: it loads its scripts, styles and fonts from the same place as the page and contacts no other site.</p>
              <h3>Fonts</h3>
              <p>The text is set in Inter regular and bold, bundled with the viewer under the SIL Open Font License 1.1. Code and error output use your system's monospace font. A workspace with a branding font has its diagrams set in that font when your computer has it.</p>
              <h3>Third-party notices</h3>
              <p>The licences and copyright notices of the software and fonts the viewer includes. <a href={noticesUrl} target="_blank" rel="noreferrer">Open as a plain text file</a>.</p>
              {notices !== null && <pre className="about-notices" tabIndex={0} aria-label="Third-party notices" data-testid="about-notices">{notices}</pre>}
              {notices === null && !failed && <p role="status">Loading the notices…</p>}
              {failed && <p role="alert">The notices could not be loaded here. Use the plain text file link above.</p>}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
