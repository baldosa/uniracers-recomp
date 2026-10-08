// node tools/web/test_settings.js: checks web/settings.js's INI editing and key names.
'use strict';
const assert = require('assert');
const vm = require('vm');
const fs = require('fs');
const src = fs.readFileSync(require('path').join(__dirname, '../../web/settings.js'), 'utf8');
const ctx = {};
vm.runInNewContext(src + '\nthis.UniSettings = UniSettings;', ctx);
const { iniGet, iniSet, sdlKeyName } = ctx.UniSettings;

const keys = '# comment\n[player1]\na       = X\nb = Z\n\n[player2]\na = X\n';
assert.strictEqual(iniGet(keys, 'player1', 'a'), 'X');
assert.strictEqual(iniGet(keys, 'PLAYER2', 'A'), 'X');
assert.strictEqual(iniGet(keys, 'player2', 'b'), undefined);
let t = iniSet(keys, 'player1', 'a', 'Right Shift');
assert.strictEqual(iniGet(t, 'player1', 'a'), 'Right Shift');
assert.strictEqual(iniGet(t, 'player2', 'a'), 'X');          // other section untouched
assert.ok(t.startsWith('# comment\n'));                       // comments kept
t = iniSet(t, 'player2', 'b', '=');                           // new key lands in its section
assert.strictEqual(iniGet(t, 'player2', 'b'), '=');
assert.ok(t.indexOf('b = =') > t.indexOf('[player2]'));
t = iniSet(t, 'Sound', 'Volume', 40);                         // new section
assert.strictEqual(iniGet(t, 'Sound', 'Volume'), '40');
assert.strictEqual(iniGet(iniSet('', 'Graphics', 'FrameBlend', 1), 'Graphics', 'FrameBlend'), '1');

assert.strictEqual(sdlKeyName('KeyQ'), 'Q');
assert.strictEqual(sdlKeyName('Digit7'), '7');
assert.strictEqual(sdlKeyName('Numpad4'), 'Keypad 4');
assert.strictEqual(sdlKeyName('ShiftRight'), 'Right Shift');
assert.strictEqual(sdlKeyName('Enter'), 'Return');
assert.strictEqual(sdlKeyName('F12'), 'F12');
assert.strictEqual(sdlKeyName('MetaLeft'), null);
console.log('ok');
