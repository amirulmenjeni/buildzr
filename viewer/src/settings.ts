// The settings registry: one list of definitions, one place that reads and writes them (localStorage).
// To add a setting: append a definition to SETTINGS. The panel, the defaults, the validation and the
// persistence all follow from it; read the value with `useStore((s) => s.settings.<id>)`.

export interface BooleanSetting { id: string; label: string; description: string; type: 'boolean'; default: boolean }
export interface ChoiceSetting { id: string; label: string; description: string; type: 'choice'; options: readonly { value: string; label: string }[]; default: string }
export type SettingDef = BooleanSetting | ChoiceSetting;

export const SETTINGS = [
  {
    id: 'zoomExpand', type: 'boolean', default: false, label: 'Zoom in to expand',
    description: 'Zooming in on a collapsed frame expands it, like clicking it.',
  },
  {
    id: 'theme', type: 'choice', default: 'system', label: 'Theme',
    options: [{ value: 'system', label: 'System' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }],
    description: 'System follows the light or dark setting of your device.',
  },
] as const satisfies readonly SettingDef[];

type Def = (typeof SETTINGS)[number];
export type SettingId = Def['id'];
type ValueOf<D> = D extends { type: 'choice'; options: readonly { value: infer V }[] } ? V : boolean;
export type SettingValues = { [D in Def as D['id']]: ValueOf<D> };
export type SettingValue = SettingValues[SettingId];

export const SETTINGS_KEY = 'buildzr-ui:settings';

export const defaults = (): SettingValues => Object.fromEntries(SETTINGS.map((d) => [d.id, d.default])) as SettingValues;

const valid = (d: SettingDef, v: unknown): boolean =>
  d.type === 'boolean' ? typeof v === 'boolean' : typeof v === 'string' && d.options.some((o) => o.value === v);

/** Defaults overlaid with whatever stored value is present and of the right type. Unknown keys and bad values are ignored. */
export function parseSettings(raw: string | null): SettingValues {
  const out = defaults();
  if (!raw) return out;
  try {
    const o: unknown = JSON.parse(raw);
    if (o === null || typeof o !== 'object' || Array.isArray(o)) return out;
    for (const d of SETTINGS) {
      const v = (o as Record<string, unknown>)[d.id];
      if (Object.prototype.hasOwnProperty.call(o, d.id) && valid(d, v)) (out as Record<string, unknown>)[d.id] = v;
    }
  } catch { /* corrupted: defaults */ }
  return out;
}

export function loadSettings(): SettingValues {
  try { return parseSettings(localStorage.getItem(SETTINGS_KEY)); } catch { return defaults(); } // storage can be blocked
}

export function saveSettings(v: SettingValues): void {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(v)); } catch { /* private window, quota: the setting still applies for this session */ }
}
