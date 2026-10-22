# Viewer settings

The viewer is the web page inside a built workspace that draws your diagrams. Its settings panel holds options that change how the canvas behaves and how the viewer looks. You can also [embed the viewer](#embed-the-viewer-in-another-page) in another page.

Each reader's browser keeps that reader's settings. Settings are not part of the workspace, `buildzr.yaml` does not set them, and a [viewer link](viewer-hash-routes.md) does not carry them. Two people who open the same link can therefore see it with different settings.

## Open the settings panel

Click the gear button at the bottom right of the left panel. On a phone, the gear is at the bottom right of the navigation drawer, which you open with the ☰ button. The settings panel opens above the gear.

To close the panel, press `Esc` or click anywhere outside it. After `Esc`, the focus returns to the gear.

## Settings

| Setting | Id | Default | What it does |
|---|---|---|---|
| Theme | `theme` | System | Light or dark. System follows the light or dark setting of your device, and changes when the device changes. See [Themes](#themes). |
| Zoom in to expand | `zoomExpand` | off | Zooming in on a collapsed frame (a box that contains other boxes) expands it, the same as clicking it. This adds one history entry, so Back returns. The frame expands when the centre of the canvas is inside it and the zoom is at least 90% of the zoom at which the frame fits the canvas. The viewer starts loading the inner diagram at 60%. Zooming out always collapses, whatever this setting is. |

## Themes

The viewer has a light and a dark theme. Pick one under **Theme** in the settings panel: **System**, **Light** or **Dark**. System is the default and follows your device.

![The viewer in the light theme: the Order Service container expanded inside the E-Commerce System, showing its two components, Order Controller and Order Repository, in the E-Commerce Platform group, with an arrow down to the Database. The model tree is on the left, the inspector on the right.](images/viewer/theme-light.png)

*The light theme: the Order Service expanded inside the E-Commerce System.*

![The same view in the dark theme: dark panels and canvas, the component boxes keep their light blue fill and black text, and the frame name Order Service is drawn in a lighter blue so it stays readable on the dark canvas.](images/viewer/theme-dark.png)

*The dark theme, the same view. The boxes keep the model's colours; the frame name is lightened.*

Both themes keep the colours of your model. Element boxes keep their fill and their text colour, including the colours your styles set. Where a colour would be hard to read on the page, the viewer lightens it in the dark theme and darkens it in the light theme: the names of expanded frames, the outlines of boxes, the arrows and their labels. Text keeps a contrast of at least 4.5:1 and the edges of boxes and controls at least 3:1, as WCAG AA asks.

The theme is applied before the page is drawn, so the viewer never flashes the other theme while it loads. A page that [embeds the viewer](#embed-the-viewer-in-another-page) chooses the theme of its frame with `theme=` or the `buildzr:theme` message.

The theme only changes the viewer. Exported PlantUML, PNG and SVG files are not affected.

## How the browser keeps the settings

The viewer stores the settings in the browser's `localStorage`, under the key `buildzr-ui:settings`, as one JSON object, for example `{"zoomExpand":true,"theme":"dark"}`. When the viewer loads, it ignores unknown keys and values of the wrong type, and uses the default instead. If the browser blocks storage, the settings still work until the page is closed.

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

Two kinds of setting exist: `boolean` (a switch) and `choice` (a row of options, such as the theme). A new kind of control, such as a number, needs two changes: a new `type` in `settings.ts` (its definition, and its validation in `parseSettings`), and a matching `case` in `Control` in `viewer/src/SettingsPanel.tsx`.

## Embed the viewer in another page

You can show the viewer inside another web page, such as a documentation page, in an `<iframe>`. In embed mode the viewer is compact: one header row, the model tree in a drawer behind the ☰ button, and an inspector that opens only when the reader selects something. The buildzr documentation uses it to draw the diagram of an example.

This section is the reference for pages that embed the viewer.

### Switch on embed mode

Add `embed=1` to the search part of the viewer's URL. The hash after it stays a normal [viewer link](viewer-hash-routes.md), so it picks what the frame opens on:

```html
<iframe src="viewer/index.html?embed=1&theme=dark#/m/shop" title="Diagram of the shop"></iframe>
```

| Parameter | Values | Default | What it does |
|---|---|---|---|
| `embed` | `1` | off | Embed mode. Without it, the URL opens the full viewer. |
| `data` | `message`, `server` | `message` | `message`: the viewer waits for your page to send the data. `server`: the viewer reads `data/` next to its `index.html`, as the full viewer does, so you can embed a built workspace. |
| `theme` | `light`, `dark`, `system` | the reader's own setting | The theme from the first paint on. Pass the theme of your page so the frame never flashes the other one. |

In embed mode the viewer:

- does not open the inspector or the bottom sheet when the frame loads, even when the link selects an element;
- never adds entries to the browser history, so the Back button of your page keeps working;
- fits any frame from 360 px to 1200 px wide without scrolling sideways. Below 768 px it uses its phone layout.

Each frame is its own page, so two frames on one page never share a selection or a route.

### Send the data

The viewer and your page talk with `postMessage`. Wait for `buildzr:ready` from the frame, then send `buildzr:load` with the files of the `data/` folder of a built workspace:

```js
const frame = document.querySelector('iframe');
addEventListener('message', (e) => {
  if (e.source !== frame.contentWindow || e.origin !== location.origin) return;
  if (e.data?.type === 'buildzr:ready') {
    frame.contentWindow.postMessage({ type: 'buildzr:load', files }, location.origin);
  }
});
```

`files` maps each path, relative to `data/` and written as `index.json` writes it, to the file's JSON text or to the parsed object. It must contain `index.json` and every file that `index.json` names. You can send `buildzr:load` again at any time, for example when the reader runs a changed example: the frame starts again from the new data.

### Send several workspaces

When your page has more than one workspace, such as a snippet that creates two, send them all in one `buildzr:load`, with `workspaces` in place of `files`. The viewer then shows a **Workspace** selector in its navigation drawer, and the reader switches between them without another message from you:

```js
frame.contentWindow.postMessage({
  type: 'buildzr:load',
  active: 'Billing',
  workspaces: [
    { name: 'Shop', files: shopFiles },
    { name: 'Billing', files: billingFiles, route: '#/m/ledger' },
  ],
}, location.origin);
```

Each entry has a `name` (shown in the selector, at most 200 characters, different from the others), `files` as above and, optionally, `build` and `route`. A message holds 1 to 50 entries. `active` names the one to show first; without it, the first. The `route` of the message, when it has one, applies to the active workspace, and otherwise the route of that entry does. Switching opens the other workspace on its own `route`, or on the landscape when it has none. It adds no history entry.

With one entry, the viewer behaves as for `files` and shows no selector. The "Open in a new tab" button opens the workspace on screen and keeps the selector in the new tab.

### Messages

Every message is an object whose `type` starts with `buildzr:`. The viewer ignores fields it does not know, and ignores a message whose fields have the wrong type.

From your page to the viewer:

| `type` | Fields | What it does |
|---|---|---|
| `buildzr:load` | `files` (required, or `workspaces`, see [Send several workspaces](#send-several-workspaces)), `build` (optional `build.json` object), `route` (optional hash such as `#/m/shop`), `title` (optional) | Draws the data. With a `build` whose `status` is `broken`, the frame shows the same broken-workspace message as the full viewer. |
| `buildzr:theme` | `theme`: `light`, `dark` or `system` | Switches the theme of the frame. The viewer does not store it. |
| `buildzr:route` | `route`: a hash, for example `#/m/shop?sel=shop/api` | Opens that place, like a [viewer link](viewer-hash-routes.md). It does not open the inspector. |

From the viewer to your page:

| `type` | Fields | When |
|---|---|---|
| `buildzr:ready` | `v`: the protocol version, `1` | The frame listens. Send `buildzr:load` after this message, not before. |
| `buildzr:loaded` | `status`: `ready`, `broken` or `error`; `error` when there is one | After each `buildzr:load`, or after the data from the server is read. |
| `buildzr:route` | `route`, `view`, `path`, `selection` | The reader moved or selected something. |
| `buildzr:workspace` | `name` | The workspace on screen changed: after a `buildzr:load` that has `workspaces`, and each time the reader picks another one. |
| `buildzr:open` | `url` | The reader opened the model in a new tab. You do not need to do anything. |

The viewer fills its frame and sends no height. Choose a height that suits your page, for example `min(560px, 80vh)`.

### Origin rules

- The viewer accepts a message only from its parent frame and only from its own origin, and it posts only to its own origin. It never uses the `*` target.
- Serve your page and the viewer from the same origin. Any static host works, such as GitHub Pages or `python -m http.server`. Pages opened from `file://` do not work, because the browser gives them no origin to check.
- Do not sandbox the frame. If you must, allow `allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox`.

### Open in a new tab

In embed mode the header has an **Open in a new tab** button. It opens the full viewer, with the model tree, the inspector and history, on the same model and the same place.

When your page sent the data, there is no URL that holds it. The new tab opens `index.html?handoff=<id>` and asks the frame that opened it for the data. It keeps a copy for the session, so reloading the tab works even after your page is closed. If the frame is gone before the tab receives the data, or the reader ran the example again since, the tab says that the diagram is no longer available and asks the reader to press the button again.

With `data=server`, the button opens the viewer's own URL without `embed`.
