import { useState } from 'react';
import { WorkspaceSwitcher } from './Workspaces';
import type { BuildInfo } from './types';

// A broken built workspace (build.json status "broken"): the viewer says so, loudly and without a way to hide it.

const FIRST = 10;

/** Stage check: the data is there and drawn below; this banner sits above the toolbar and pushes it down. */
export function BrokenBanner({ build }: { build: BuildInfo }) {
  const [open, setOpen] = useState(false);
  const errors = build.errors ?? [];
  return (
    <div className="broken-area" data-testid="broken-banner">
      <div role="alert" className="broken-banner">
        <strong>This workspace is broken: the data failed its checks.</strong>
        {errors.length > 0 && (
          <button className="broken-toggle" aria-expanded={open} aria-controls="broken-errors" onClick={() => setOpen(!open)}>
            {open ? 'Hide the errors' : `Show the ${errors.length === 1 ? 'error' : `${errors.length} errors`}`}
          </button>
        )}
      </div>
      {open && (
        <div id="broken-errors" className="broken-errors" role="region" aria-label="Errors of this workspace" tabIndex={0}>
          <pre>{errors.join('\n')}</pre>
        </div>
      )}
    </div>
  );
}

/** Stage model or layout: there is no data, so no diagram; this page takes its place. */
export function BrokenScreen({ build }: { build: BuildInfo }) {
  const errors = build.errors ?? [];
  const file = build.input?.file;
  return (
    <main className="broken-screen" data-testid="broken-screen">
      <div role="alert" className="broken-banner">
        <strong>This workspace is broken: building it failed at the {build.stage ?? 'unknown'} step.</strong>
      </div>
      <div className="broken-body">
        <WorkspaceSwitcher />
        {build.workspace && <h1>{build.workspace}</h1>}
        {errors.length > 0 && (
          <>
            <h2>{errors.length > FIRST ? `The first ${FIRST} of ${errors.length} errors` : errors.length === 1 ? 'The error' : 'The errors'}</h2>
            <pre className="broken-list">{errors.slice(0, FIRST).join('\n')}</pre>
          </>
        )}
        <p>
          Fix the error in {file ? <code>{file}</code> : 'the model file'} and run <code>buildzr build</code> again, or restart{' '}
          <code>buildzr serve</code>.
        </p>
      </div>
    </main>
  );
}
