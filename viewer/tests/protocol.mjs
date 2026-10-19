// Unit tests without a browser: the embed protocol (protocol.ts). Run: npm run test:unit
import { T } from './lib.mjs';
import { parseMessage, parseMode, trusted } from '../src/protocol.ts';

const t = new T('protocol');
const files = { 'index.json': '{}', 'model.1.json': { a: 1 } };

// ---- mode (search part of the URL)
t.eq(parseMode(''), { embed: false, data: 'message', theme: null }, 'no search: standalone');
t.eq(parseMode('?embed=1'), { embed: true, data: 'message', theme: null }, 'embed=1');
t.eq(parseMode('?embed=1&data=server&theme=dark'), { embed: true, data: 'server', theme: 'dark' }, 'embed, server data, dark');
t.eq(parseMode('?embed=1&theme=purple&data=ftp').theme, null, 'unknown theme ignored');
t.eq(parseMode('?embed=1&theme=purple&data=ftp').data, 'message', 'unknown data ignored');
t.eq(parseMode('?embed=true').embed, false, 'embed must be 1');
t.eq(parseMode('?theme=dark').theme, null, 'theme parameter only in embed mode');

// ---- messages: valid
t.eq(parseMessage({ type: 'buildzr:load', files }), { type: 'buildzr:load', files, build: null, route: null, title: null }, 'minimal load');
t.eq(parseMessage({ type: 'buildzr:load', files, build: { status: 'broken', stage: 'check' }, route: '#/m/x?sel=x/y', title: 'T', extra: 1 })?.route, '#/m/x?sel=x/y', 'full load, extra field ignored');
t.eq(parseMessage({ type: 'buildzr:theme', theme: 'dark' }), { type: 'buildzr:theme', theme: 'dark' }, 'theme dark');
t.eq(parseMessage({ type: 'buildzr:theme', theme: 'system' })?.theme, 'system', 'theme system');
t.eq(parseMessage({ type: 'buildzr:route', route: '#/v/key' }), { type: 'buildzr:route', route: '#/v/key' }, 'route');
t.eq(parseMessage({ type: 'buildzr:route', route: '' })?.route, '', 'empty route = landscape');

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

console.log(`\nprotocol: ${t.checks} checks, ${t.fails} failed`);
process.exit(t.fails ? 1 : 0);
