// Unit tests without a browser: the embed protocol (protocol.ts). Run: npm run test:unit
import { T } from './lib.mjs';
import { parseMessage, parseMode, trusted, newId } from '../src/protocol.ts';

const t = new T('protocol');
const ID = 'a'.repeat(32);
const files = { 'index.json': '{}', 'model.1.json': { a: 1 } };

// ---- mode (search part of the URL)
t.eq(parseMode(''), { embed: false, data: 'message', theme: null, handoff: null }, 'no search: standalone');
t.eq(parseMode('?embed=1'), { embed: true, data: 'message', theme: null, handoff: null }, 'embed=1');
t.eq(parseMode('?embed=1&data=server&theme=dark'), { embed: true, data: 'server', theme: 'dark', handoff: null }, 'embed, server data, dark');
t.eq(parseMode('?embed=1&theme=purple&data=ftp').theme, null, 'unknown theme ignored');
t.eq(parseMode('?embed=1&theme=purple&data=ftp').data, 'message', 'unknown data ignored');
t.eq(parseMode('?embed=true').embed, false, 'embed must be 1');
t.eq(parseMode('?theme=dark').theme, null, 'theme parameter only in embed mode');
t.eq(parseMode(`?handoff=${ID}`).handoff, ID, 'handoff id');
t.eq(parseMode('?handoff=../../x').handoff, null, 'bad handoff id ignored');
t.eq(parseMode(`?embed=1&handoff=${ID}`).handoff, null, 'no handoff inside an embed');

// ---- messages: valid
t.eq(parseMessage({ type: 'buildzr:load', files }), { type: 'buildzr:load', files, build: null, route: null, title: null, group: null }, 'minimal load');
t.eq(parseMessage({ type: 'buildzr:load', files, build: { status: 'broken', stage: 'check' }, route: '#/m/x?sel=x/y', title: 'T', extra: 1 })?.route, '#/m/x?sel=x/y', 'full load, extra field ignored');
t.eq(parseMessage({ type: 'buildzr:theme', theme: 'dark' }), { type: 'buildzr:theme', theme: 'dark' }, 'theme dark');
t.eq(parseMessage({ type: 'buildzr:theme', theme: 'system' })?.theme, 'system', 'theme system');
t.eq(parseMessage({ type: 'buildzr:route', route: '#/v/key' }), { type: 'buildzr:route', route: '#/v/key' }, 'route');
t.eq(parseMessage({ type: 'buildzr:route', route: '' })?.route, '', 'empty route = landscape');
t.eq(parseMessage({ type: 'buildzr:handoff-request', id: ID }), { type: 'buildzr:handoff-request', id: ID }, 'handoff request');
t.eq(parseMessage({ type: 'buildzr:handoff', id: ID, files, build: null })?.type, 'buildzr:handoff', 'handoff answer');
t.eq(parseMessage({ type: 'buildzr:handoff-missing', id: ID })?.type, 'buildzr:handoff-missing', 'handoff missing');

// ---- messages: several workspaces in one load (the switcher)
const wsA = { name: 'Shop', files, route: '#/m/shop' }, wsB = { name: 'Billing', files: { 'index.json': '{"b":1}' }, build: { status: 'broken' } };
const two = parseMessage({ type: 'buildzr:load', workspaces: [wsA, wsB], title: 'T' });
t.eq(two?.group?.workspaces.map((w) => w.name), ['Shop', 'Billing'], 'workspaces: names in order');
t.eq(two?.group?.active, 'Shop', 'workspaces: the first is active by default');
t.eq([two?.files, two?.route, two?.build], [files, '#/m/shop', null], 'workspaces: files, route and build are the active one\'s');
const second = parseMessage({ type: 'buildzr:load', workspaces: [wsA, wsB], active: 'Billing', route: '#/v/x' });
t.eq([second?.group?.active, second?.files, second?.build, second?.route], ['Billing', wsB.files, { status: 'broken' }, '#/v/x'], 'workspaces: active picks the data, the message route wins');
t.eq(parseMessage({ type: 'buildzr:load', files, workspaces: [wsB] })?.files, wsB.files, 'workspaces win over files');
t.eq(parseMessage({ type: 'buildzr:load', workspaces: [wsA] })?.group?.workspaces.length, 1, 'one workspace is accepted (the switcher hides itself)');
t.eq(parseMessage({ type: 'buildzr:handoff', id: ID, workspaces: [wsA, wsB], active: 'Billing' })?.group?.active, 'Billing', 'handoff carries the set');
t.eq(parseMessage({ type: 'buildzr:handoff', id: ID, files })?.group, null, 'handoff without a set');
const badSets = [
  [], 'x', {}, [null], [{ files }], [{ name: '', files }], [{ name: 'x'.repeat(201), files }], [{ name: 'A' }], [{ name: 'A', files: {} }],
  [wsA, { ...wsB, name: 'Shop' }], [{ ...wsA, route: 'javascript:1' }], [{ ...wsA, build: 'ok' }],
  Array.from({ length: 51 }, (_, i) => ({ name: 'w' + i, files })),
];
for (const b of badSets) t.eq(parseMessage({ type: 'buildzr:load', workspaces: b }), null, `invalid workspaces ignored: ${JSON.stringify(b)?.slice(0, 60)}`);
t.eq(parseMessage({ type: 'buildzr:load', workspaces: [wsA, wsB], active: 'Nope' }), null, 'active must name a workspace');
t.eq(parseMessage({ type: 'buildzr:load', workspaces: [wsA], active: 3 }), null, 'active must be a string');
t.eq(parseMessage({ type: 'buildzr:handoff', id: ID, workspaces: [] }), null, 'handoff: empty set ignored');

// ---- messages: invalid (each is ignored)
const bad = [
  null, undefined, 'buildzr:load', 42, [], { type: 1 }, { type: 'load', files }, { type: 'buildzr:unknown' },
  { type: 'buildzr:load' }, { type: 'buildzr:load', files: [] }, { type: 'buildzr:load', files: {} },
  { type: 'buildzr:load', files: { 'model.json': '{}' } }, { type: 'buildzr:load', files: { 'index.json': 3 } },
  { type: 'buildzr:load', files: { 'index.json': null } }, { type: 'buildzr:load', files, build: 'ok' },
  { type: 'buildzr:load', files, route: 'javascript:alert(1)' }, { type: 'buildzr:load', files, route: 5 },
  { type: 'buildzr:load', files, title: 7 }, { type: 'buildzr:load', files: { 'index.json': '{}', ['x'.repeat(600)]: '{}' } },
  { type: 'buildzr:theme' }, { type: 'buildzr:theme', theme: 'blue' }, { type: 'buildzr:theme', theme: true },
  { type: 'buildzr:route' }, { type: 'buildzr:route', route: '/m/x' }, { type: 'buildzr:route', route: 'https://evil.example/#/m' },
  { type: 'buildzr:route', route: '#' + 'x'.repeat(5000) },
  { type: 'buildzr:handoff-request' }, { type: 'buildzr:handoff-request', id: 'short' }, { type: 'buildzr:handoff-request', id: ID.toUpperCase() },
  { type: 'buildzr:handoff', id: ID }, { type: 'buildzr:handoff', id: 'x', files },
];
for (const b of bad) t.eq(parseMessage(b), null, `invalid message ignored: ${JSON.stringify(b)?.slice(0, 80)}`);
t.ok(parseMessage({ type: 'buildzr:load', files, title: 'x'.repeat(500) }).title.length === 200, 'title cut to 200 characters');

// ---- origin rule
const parent = {}, other = {};
t.ok(trusted({ origin: 'https://a.example', source: parent }, parent, 'https://a.example'), 'same origin, the parent: trusted');
t.ok(!trusted({ origin: 'https://b.example', source: parent }, parent, 'https://a.example'), 'another origin: refused');
t.ok(!trusted({ origin: 'https://a.example', source: other }, parent, 'https://a.example'), 'another window of the same origin: refused');
t.ok(!trusted({ origin: 'null', source: parent }, parent, 'null'), 'opaque origins (file://, sandboxed): refused');
t.ok(!trusted({ origin: 'https://a.example', source: null }, null, 'https://a.example'), 'no parent (not in a frame): refused');
t.ok(/^[0-9a-f]{32}$/.test(newId()) && newId() !== newId(), 'handoff ids: 32 hex, random');

console.log(`\nprotocol: ${t.checks} checks, ${t.fails} failed`);
process.exit(t.fails ? 1 : 0);
