import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { SETTINGS, type SettingDef, type SettingId, type SettingValue } from './settings';
import { useStore } from './store';

function Control({ def }: { def: SettingDef }): ReactNode {
  const sid = def.id as SettingId;
  const value = useStore((s) => s.settings[sid]);
  const set = useStore((s) => s.setSetting);
  const id = useId();
  switch (def.type) {
    case 'boolean':
      return (
        <div className="setting">
          <input id={id} type="checkbox" role="switch" checked={value === true} aria-describedby={`${id}-d`} data-setting={def.id} onChange={(e) => set(sid, e.target.checked)} />
          <label htmlFor={id}>{def.label}</label>
          <p id={`${id}-d`} className="setting-desc">{def.description}</p>
        </div>
      );
    case 'choice':
      return (
        <fieldset className="setting choice" aria-describedby={`${id}-d`} data-setting={def.id}>
          <legend>{def.label}</legend>
          <div className="segmented">
            {def.options.map((o) => (
              <label key={o.value} className={value === o.value ? 'on' : undefined}>
                <input type="radio" name={id} value={o.value} checked={value === o.value} onChange={() => set(sid, o.value as SettingValue)} />
                {o.label}
              </label>
            ))}
          </div>
          <p id={`${id}-d`} className="setting-desc">{def.description}</p>
        </fieldset>
      );
  }
}

/** The gear button (bottom-right of the left panel) and its popover; `extra` sits at the bottom-left of the same row. */
export function SettingsButton({ extra }: { extra?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const gear = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const title = useId();
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    panel.current?.querySelector<HTMLElement>('input, button')?.focus();
    const away = (e: PointerEvent) => {
      const t = e.target as Node;
      if (!panel.current?.contains(t) && !gear.current?.contains(t)) setOpen(false);
    };
    addEventListener('pointerdown', away);
    return () => removeEventListener('pointerdown', away);
  }, [open]);

  const close = (): void => { setOpen(false); gear.current?.focus(); };
  return (
    <div className="left-foot">
      {extra}
      {open && (
        <div ref={panel} id={panelId} className="settings-panel" role="dialog" aria-labelledby={title} data-testid="settings-panel"
             onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); close(); } }}>
          <h2 id={title}>Settings</h2>
          {SETTINGS.map((d) => <Control key={d.id} def={d} />)}
        </div>
      )}
      <button ref={gear} className="gear" aria-label="Settings" aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? panelId : undefined}
              onClick={() => (open ? close() : setOpen(true))}>
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
          <path fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round"
                d="M10.3 2.8h3.4l.5 2.4 1.6.7 2.1-1.3 2.4 2.4-1.3 2.1.7 1.6 2.4.5v3.4l-2.4.5-.7 1.6 1.3 2.1-2.4 2.4-2.1-1.3-1.6.7-.5 2.4h-3.4l-.5-2.4-1.6-.7-2.1 1.3-2.4-2.4 1.3-2.1-.7-1.6-2.4-.5v-3.4l2.4-.5.7-1.6-1.3-2.1 2.4-2.4 2.1 1.3 1.6-.7z" />
          <circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.8" />
        </svg>
      </button>
    </div>
  );
}
