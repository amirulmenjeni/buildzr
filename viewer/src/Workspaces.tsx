import { useId } from 'react';
import { useStore } from './store';

/** Pick among the workspaces of one model file, a served catalogue or a Run Code snippet. Not drawn for fewer than two. */
export function WorkspaceSwitcher() {
  const id = useId();
  const list = useStore((s) => s.workspaces);
  const active = useStore((s) => s.activeWorkspace);
  const switchWorkspace = useStore((s) => s.switchWorkspace);
  if (list.length < 2 || !active || !list.some((w) => w.id === active)) return null;
  return (
    <div className="wsswitch" data-testid="workspace-switcher">
      <label htmlFor={id} className="h">Workspace</label>
      <select id={id} value={active} onChange={(e) => switchWorkspace(e.target.value)}>
        {list.map((w) => <option key={w.id} value={w.id}>{w.label}</option>)}
      </select>
    </div>
  );
}
