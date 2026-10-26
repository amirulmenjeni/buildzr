// Step through a dynamic view: a small bar over the canvas, shown on dynamic views only. The layout never changes:
// a step only marks its arrows and dims what comes later (compose.ts). The step is not in the hash.
import { useEffect, useMemo, useRef, type KeyboardEvent, type ReactNode } from 'react';
import { stepsOf, stepText } from './steps';
import { useStore } from './store';

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"><path fill="currentColor" d={d} /></svg>
);
const ICONS = {
  first: 'M3 3h2v10H3zM13 3v10L6 8z',
  prev: 'M10.6 2.3 4.9 8l5.7 5.7 1.4-1.4L7.7 8l4.3-4.3z',
  play: 'M4 2.5v11L13.5 8z',
  pause: 'M4 3h3v10H4zM9 3h3v10H9z',
  next: 'M5.4 2.3 11.1 8l-5.7 5.7L4 12.3 8.3 8 4 3.7z',
  close: 'M3.7 2.3 8 6.6l4.3-4.3 1.4 1.4L9.4 8l4.3 4.3-1.4 1.4L8 9.4l-4.3 4.3-1.4-1.4L6.6 8 2.3 3.7z',
};

function Btn({ label, keys, shortcut, off, onClick, children, testid, btnRef }: {
  label: string; keys?: string; shortcut?: string; off?: boolean; onClick: () => void; children: ReactNode; testid: string; btnRef?: React.Ref<HTMLButtonElement>;
}) {
  // aria-disabled, not disabled: the button keeps the focus when it reaches the first or the last step
  return (
    <button ref={btnRef} type="button" className="steps-btn" aria-label={label} title={keys ? `${label} (${keys})` : label} aria-keyshortcuts={shortcut} data-testid={testid}
            aria-disabled={off ? 'true' : undefined} onClick={() => { if (!off) onClick(); }}>{children}</button>
  );
}

export function Playback() {
  const m = useStore((s) => s.m)!;
  const view = useStore((s) => s.view);
  const scenes = useStore((s) => s.scenes);
  const step = useStore((s) => s.step);
  const playing = useStore((s) => s.playing);
  const setStep = useStore((s) => s.setStep);
  const v = view ? m.viewByKey.get(view) : undefined;
  const scene = v ? scenes[v.scene] : undefined;
  const steps = useMemo(() => stepsOf(scene, v?.kind), [scene, v]);
  const n = steps.length;
  const playRef = useRef<HTMLButtonElement>(null);

  /** "Web App → API: Posts the order to"; the edges of a parallel step are joined. */
  const describe = (i: number, to: string): string => !scene ? '' : steps[i - 1].edges.map((id) => {
    const e = scene.edges.find((x) => x.id === id)!;
    const name = (end: typeof e.source): string => (typeof end === 'string' ? m.byId.get(end)?.name ?? end : '');
    const text = stepText(scene, id, (r) => m.relById.get(r)?.description ?? null);
    return `${name(e.source)} ${to} ${name(e.target)}${text ? `: ${text}` : ''}`;
  }).join('; ');
  const go = (i: number, play = false): void => {
    const k = Math.max(0, Math.min(n, i));
    setStep(k, k === 0 ? `Showing the whole diagram, ${n} steps` : `Step ${k} of ${n}: ${describe(k, 'to')}`, play && k < n);
  };
  const latest = useRef(go);
  latest.current = go;

  // Play: the next step after stepMs, until the last one. Pressing any other control pauses.
  useEffect(() => {
    if (!playing) return;
    const t = window.setTimeout(() => latest.current(useStore.getState().step + 1, true), window.__viewer.stepMs);
    return () => window.clearTimeout(t);
  }, [playing, step]);

  if (!v || n === 0) return null;
  const togglePlay = (): void => {
    if (playing) { setStep(step, `Paused at step ${step} of ${n}`); return; }
    if (step === 0 || step >= n) go(1, true); // from the start (again)
    else setStep(step, `Playing from step ${step} of ${n}`, true);
  };
  const onKeyDown = (ev: KeyboardEvent): void => {
    const k = ev.key;
    const to = k === 'ArrowRight' ? (step < n ? step + 1 : null) : k === 'ArrowLeft' ? (step > 1 ? step - 1 : null)
      : k === 'Home' ? 1 : k === 'End' ? n : k === 'Escape' && step > 0 ? 0 : null;
    if (to === null) return;
    ev.preventDefault();
    ev.stopPropagation(); // Escape here ends the stepping, it does not close the drawer or the inspector
    go(to);
    if (to === 0) playRef.current?.focus();
  };
  const playLabel = playing ? 'Pause' : step === 0 ? 'Play the steps' : step >= n ? 'Play again from the first step' : 'Play';
  return (
    <div className="steps" role="group" aria-label="Steps of this dynamic view" data-testid="steps" data-step={step} data-playing={playing ? 'true' : undefined} onKeyDown={onKeyDown}>
      <div className="steps-controls">
        <Btn label="First step" keys="Home" shortcut="Home" off={step === 1} onClick={() => go(1)} testid="steps-first"><Icon d={ICONS.first} /></Btn>
        <Btn label="Previous step" keys="Left arrow" shortcut="ArrowLeft" off={step <= 1} onClick={() => go(step - 1)} testid="steps-prev"><Icon d={ICONS.prev} /></Btn>
        <Btn label={playLabel} onClick={togglePlay} testid="steps-play" btnRef={playRef}><Icon d={playing ? ICONS.pause : ICONS.play} /></Btn>
        <Btn label="Next step" keys="Right arrow" shortcut="ArrowRight" off={step >= n} onClick={() => go(step + 1)} testid="steps-next"><Icon d={ICONS.next} /></Btn>
        <span className="steps-count" data-testid="steps-count">{step === 0 ? `${n} step${n === 1 ? '' : 's'}` : `Step ${step} of ${n}`}</span>
        {step > 0 && (
          <Btn label="Show the whole diagram" keys="Escape" shortcut="Escape" onClick={() => { go(0); playRef.current?.focus(); }} testid="steps-close"><Icon d={ICONS.close} /></Btn>
        )}
      </div>
      {step > 0 && <p className="steps-text" data-testid="steps-text">{describe(step, '→')}</p>}
    </div>
  );
}
