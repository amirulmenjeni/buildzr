# UI settings

The buildzr viewer has a small settings panel for options that change how the canvas behaves.

## Where it is

Click the gear button at the bottom-right of the left panel (on a phone: the bottom-right of the navigation drawer, opened with the ☰ button). The panel opens above the button. Press `Esc` to close it; focus returns to the gear. Clicking anywhere outside also closes it.

## Settings

| Setting | Id | Default | What it does |
|---|---|---|---|
| Zoom in to expand | `zoomExpand` | off | Zooming in on a collapsed frame expands it, the same as clicking it (one history entry, Back returns). Needs the viewport centre inside the frame and the frame zoomed to at least 90% of the zoom at which it fits the canvas. The child scene is prefetched from 60%. Zooming out always collapses, whatever this is set to. |

## How settings are kept

Settings are stored in the browser's `localStorage` under the key `buildzr-ui:settings` as one JSON object, for example `{"zoomExpand":true}`. On load, unknown keys and values of the wrong type are ignored and the default is used. If storage is blocked the settings still work for the current session.

Tests and scripts can read the current values from `window.__viewer.settings`.

## Adding a setting

All settings are defined in one list, `SETTINGS` in `viewer/src/settings.ts`. Add an entry:

```ts
{ id: 'myOption', type: 'boolean', default: false, label: 'Short label', description: 'One line that says what it does.' },
```

The panel, the defaults, the validation and the persistence follow from the entry. Read it where you need it:

```ts
const on = useStore((s) => s.settings.myOption);   // in a component
useStore.getState().settings.myOption;             // anywhere else
```

A new kind of control (a choice, a number) needs a new `type` in `settings.ts` (its definition and its validation in `parseSettings`) and a matching `case` in `Control` in `viewer/src/SettingsPanel.tsx`.
