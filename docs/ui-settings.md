# Viewer settings

The viewer is the web page inside a built workspace that draws your diagrams. Its settings panel holds options that change how the canvas behaves.

Each reader's browser keeps that reader's settings. Settings are not part of the workspace, `buildzr.yaml` does not set them, and a [viewer link](viewer-hash-routes.md) does not carry them. Two people who open the same link can therefore see it with different settings.

## Open the settings panel

Click the gear button at the bottom right of the left panel. On a phone, the gear is at the bottom right of the navigation drawer, which you open with the ☰ button. The settings panel opens above the gear.

To close the panel, press `Esc` or click anywhere outside it. After `Esc`, the focus returns to the gear.

## Settings

| Setting | Id | Default | What it does |
|---|---|---|---|
| Zoom in to expand | `zoomExpand` | off | Zooming in on a collapsed frame (a box that contains other boxes) expands it, the same as clicking it. This adds one history entry, so Back returns. The frame expands when the centre of the canvas is inside it and the zoom is at least 90% of the zoom at which the frame fits the canvas. The viewer starts loading the inner diagram at 60%. Zooming out always collapses, whatever this setting is. |

## How the browser keeps the settings

The viewer stores the settings in the browser's `localStorage`, under the key `buildzr-ui:settings`, as one JSON object, for example `{"zoomExpand":true}`. When the viewer loads, it ignores unknown keys and values of the wrong type, and uses the default instead. If the browser blocks storage, the settings still work until the page is closed.

Tests and scripts can read the current values from `window.__viewer.settings`.

## Add a setting (for contributors)

All settings are defined in one list, `SETTINGS` in `viewer/src/settings.ts`. To add a setting, add an entry:

```ts
{ id: 'myOption', type: 'boolean', default: false, label: 'Short label', description: 'One line that says what it does.' },
```

The panel, the default, the validation and the storage follow from the entry. Read the value where you need it:

```ts
const on = useStore((s) => s.settings.myOption);   // in a component
useStore.getState().settings.myOption;             // anywhere else
```

A new kind of control, such as a choice or a number, needs two changes: a new `type` in `settings.ts` (its definition, and its validation in `parseSettings`), and a matching `case` in `Control` in `viewer/src/SettingsPanel.tsx`.
