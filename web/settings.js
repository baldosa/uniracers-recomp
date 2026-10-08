// Settings panel for the web build.
//
// The game reads config.ini and keybinds.ini (IndexedDB-backed /persist)
// when it starts, exactly like the desktop build; this panel edits those
// files, so a change applies on the next start. Screen size and the FPS
// overlay are page-only and live in localStorage.
'use strict';

const UniSettings = (() => {
  const CFG = '/persist/config.ini', KEYS = '/persist/keybinds.ini', SRAM = '/persist/saves/save.srm';
  // SNES buttons in display order: [keybinds.ini key, label].
  const BUTTONS = [['up', 'Up'], ['down', 'Down'], ['left', 'Left'], ['right', 'Right'],
    ['a', 'A'], ['b', 'B'], ['x', 'X'], ['y', 'Y'], ['l', 'L'], ['r', 'R'],
    ['start', 'Start'], ['select', 'Select']];
  const KEY_DEFAULTS = { up: 'Up', down: 'Down', left: 'Left', right: 'Right', a: 'X', b: 'Z',
    x: 'S', y: 'A', l: 'C', r: 'V', start: 'Return', select: 'Right Shift' };
  // Player 2 on the same keyboard: clear of player 1's keys and the hotkeys.
  const KEY_P2 = { up: 'I', down: 'K', left: 'J', right: 'L', a: 'H', b: 'G',
    x: 'Y', y: 'T', l: 'U', r: 'O', start: '1', select: '2' };
  // config.ini [GamepadMap] Controls: SDL gamepad button per SNES button, in this order.
  const PAD_ORDER = ['up', 'down', 'left', 'right', 'select', 'start', 'a', 'b', 'x', 'y', 'l', 'r'];
  const PAD_DEFAULTS = ['DpadUp', 'DpadDown', 'DpadLeft', 'DpadRight', 'Back', 'Start', 'B', 'A', 'Y', 'X', 'Lb', 'Rb'];
  // Browser "standard" gamepad layout index -> SDL gamepad button name.
  const STD_PAD = ['A', 'B', 'X', 'Y', 'Lb', 'Rb', 'L2', 'R2', 'Back', 'Start', 'L3', 'R3',
    'DpadUp', 'DpadDown', 'DpadLeft', 'DpadRight', 'Guide'];
  const PAD_LABEL = { A: 'A', B: 'B', X: 'X', Y: 'Y', Lb: 'LB', Rb: 'RB', L2: 'LT', R2: 'RT', L1: 'LB', R1: 'RB',
    Back: 'Back', Start: 'Start', L3: 'L-stick', R3: 'R-stick', Guide: 'Home',
    DpadUp: 'D-pad ↑', DpadDown: 'D-pad ↓', DpadLeft: 'D-pad ←', DpadRight: 'D-pad →' };

  // KeyboardEvent.code -> SDL scancode name (what keybinds.ini holds).
  const CODE_NAMES = {
    Enter: 'Return', Space: 'Space', Tab: 'Tab', CapsLock: 'CapsLock',
    ArrowUp: 'Up', ArrowDown: 'Down', ArrowLeft: 'Left', ArrowRight: 'Right',
    ShiftLeft: 'Left Shift', ShiftRight: 'Right Shift', ControlLeft: 'Left Ctrl', ControlRight: 'Right Ctrl',
    AltLeft: 'Left Alt', AltRight: 'Right Alt', Minus: '-', Equal: '=', BracketLeft: '[', BracketRight: ']',
    Backslash: '\\', Semicolon: ';', Quote: "'", Backquote: '`', Comma: ',', Period: '.', Slash: '/',
    Insert: 'Insert', Home: 'Home', PageUp: 'PageUp', Delete: 'Delete', End: 'End', PageDown: 'PageDown',
    NumpadEnter: 'Keypad Enter', NumpadAdd: 'Keypad +', NumpadSubtract: 'Keypad -',
    NumpadMultiply: 'Keypad *', NumpadDivide: 'Keypad /', NumpadDecimal: 'Keypad .',
  };
  function sdlKeyName(code) {
    let m;
    if ((m = code.match(/^Key([A-Z])$/))) return m[1];
    if ((m = code.match(/^Digit(\d)$/))) return m[1];
    if ((m = code.match(/^Numpad(\d)$/))) return 'Keypad ' + m[1];
    if (/^F([1-9]|1[0-2])$/.test(code)) return code;
    return CODE_NAMES[code] || null;
  }

  // ---- minimal INI editing that keeps every other line as it is ----
  const SEC = /^\s*\[(.+?)\]/, KV = /^\s*([^=#;\s][^=]*?)\s*=\s*(.*?)\s*$/;
  function iniGet(text, sec, key) {
    let cur = '';
    for (const line of text.split('\n')) {
      const s = line.match(SEC);
      if (s) { cur = s[1].toLowerCase(); continue; }
      const kv = line.match(KV);
      if (kv && cur === sec.toLowerCase() && kv[1].toLowerCase() === key.toLowerCase()) return kv[2];
    }
    return undefined;
  }
  function iniSet(text, sec, key, value) {
    const lines = text ? text.replace(/\n$/, '').split('\n') : [];
    let cur = '', last = -1;
    for (let i = 0; i < lines.length; i++) {
      const s = lines[i].match(SEC);
      if (s) { cur = s[1].toLowerCase(); if (cur === sec.toLowerCase()) last = i; continue; }
      if (cur !== sec.toLowerCase()) continue;
      const kv = lines[i].match(KV);
      if (kv && kv[1].toLowerCase() === key.toLowerCase()) { lines[i] = `${key} = ${value}`; return lines.join('\n') + '\n'; }
      if (lines[i].trim()) last = i;
    }
    if (last < 0) lines.push('', `[${sec}]`, `${key} = ${value}`);
    else lines.splice(last + 1, 0, `${key} = ${value}`);
    return lines.join('\n').replace(/^\n+/, '') + '\n';
  }

  const read = (p) => { try { return new TextDecoder().decode(FS.readFile(p)); } catch (e) { return ''; } };
  const store = {
    get(k, d) { try { const v = localStorage.getItem('uni.' + k); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('uni.' + k, v); } catch (e) {} },
  };
  const truthy = (v) => /^(1|true|yes|on)$/i.test(String(v || '').trim());

  // ---- model: what the dialog edits ----
  function load() {
    const cfg = read(CFG), keys = read(KEYS);
    const pads = [1, 2].map((p) => {
      const list = (iniGet(cfg, 'GamepadMap', p === 1 ? 'Controls' : 'ControlsP2') || '').split(',').map((s) => s.trim());
      return list.length === 12 && list.every(Boolean) ? list : PAD_DEFAULTS.slice();
    });
    return {
      keys: [1, 2].map((p) => Object.fromEntries(BUTTONS.map(([k]) =>
        [k, iniGet(keys, 'player' + p, k) || KEY_DEFAULTS[k]]))),
      pads,
      // The host's own defaults when [Controller] is absent: P1 keyboard, P2 nothing.
      src: [1, 2].map((p) => +(iniGet(cfg, 'Controller', 'SourceP' + p) ?? (p === 1 ? 1 : 0))),
      aspect: iniGet(cfg, 'Graphics', 'DisplayAspect') || '4:3',
      linear: truthy(iniGet(cfg, 'Graphics', 'LinearFiltering')),
      blend: truthy(iniGet(cfg, 'Graphics', 'FrameBlend')),
      sprites: iniGet(cfg, 'Graphics', 'NoSpriteLimits') === undefined || truthy(iniGet(cfg, 'Graphics', 'NoSpriteLimits')),
      audio: iniGet(cfg, 'Sound', 'EnableAudio') === undefined || truthy(iniGet(cfg, 'Sound', 'EnableAudio')),
      volume: +(iniGet(cfg, 'Sound', 'Volume') || 100),
      hotkeys: hotkeysOf(cfg),
      size: store.get('size', 'fit'),
      fps: store.get('fps', '0') === '1',
    };
  }
  function save(m) {
    let cfg = read(CFG), keys = read(KEYS);
    for (const p of [1, 2]) {
      for (const [k] of BUTTONS) keys = iniSet(keys, 'player' + p, k, m.keys[p - 1][k]);
      cfg = iniSet(cfg, 'GamepadMap', p === 1 ? 'Controls' : 'ControlsP2', m.pads[p - 1].join(', '));
      cfg = iniSet(cfg, 'Controller', 'SourceP' + p, m.src[p - 1]);
    }
    cfg = iniSet(cfg, 'Graphics', 'DisplayAspect', m.aspect);
    cfg = iniSet(cfg, 'Graphics', 'LinearFiltering', m.linear ? 1 : 0);
    cfg = iniSet(cfg, 'Graphics', 'FrameBlend', m.blend ? 1 : 0);
    cfg = iniSet(cfg, 'Graphics', 'NoSpriteLimits', m.sprites ? 1 : 0);
    cfg = iniSet(cfg, 'Sound', 'EnableAudio', m.audio ? 1 : 0);
    cfg = iniSet(cfg, 'Sound', 'Volume', m.volume);
    FS.writeFile(CFG, cfg);
    FS.writeFile(KEYS, keys);
    store.set('size', m.size);
    store.set('fps', m.fps ? '1' : '0');
  }
  // Single-key hotkeys ([KeyMap] Turbo = Tab, Pause = Shift+p, ...): a game
  // button on the same key would fire both.
  function hotkeysOf(cfg) {
    const out = {};
    const names = { Turbo: 'Turbo', PauseDimmed: 'Pause', DisplayPerf: 'Performance overlay',
      ToggleRenderer: 'Switch renderer', SaveStateMenu: 'Save-state menu', Rewind: 'Rewind' };
    const defaults = { Turbo: 'Tab', PauseDimmed: 'p', DisplayPerf: 'f', ToggleRenderer: 'r', SaveStateMenu: 'F11', Rewind: 'F12' };
    for (const k in names) {
      const v = (iniGet(cfg, 'KeyMap', k) ?? defaults[k]).trim();
      if (v && !v.includes('+')) out[v.toLowerCase()] = names[k];
    }
    for (let i = 1; i <= 10; i++) out['f' + i] = 'Load state ' + i;
    return out;
  }

  // ---- page-only display settings ----
  const ASPECT = { '4:3': 4 / 3, '8:7': 8 / 7, '1:1': 1 };
  function applyPage(m, canvas) {
    const ar = ASPECT[m.aspect] || 4 / 3;
    canvas.style.aspectRatio = String(ar);
    canvas.style.imageRendering = m.linear ? 'auto' : 'pixelated';
    canvas.style.maxWidth = m.size === 'fit' ? `min(100%, calc((100vh - 110px) * ${ar}))` : m.size + 'px';
  }

  // ---- the dialog ----
  const $ = (id) => document.getElementById(id);
  let model, player = 0, capture = null;

  function cancelCapture() {
    if (!capture) return;
    capture.stop();
    capture = null;
    render();
  }
  function keyButton(k) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'bind';
    const v = model.keys[player][k];
    const hot = model.hotkeys[v.toLowerCase()];
    b.textContent = v === 'None' ? '—' : v;
    if (hot) { b.classList.add('warn'); b.title = `Also the ${hot} hotkey`; }
    b.onclick = () => {
      cancelCapture();
      b.textContent = 'Press a key…';
      b.classList.add('listening');
      const onKey = (e) => {
        e.preventDefault();
        e.stopImmediatePropagation();
        if (e.code === 'Escape') return cancelCapture();
        const name = e.code === 'Backspace' || e.code === 'Delete' ? 'None' : sdlKeyName(e.code);
        if (!name) { b.textContent = 'Not supported, try another'; return; }
        const keys = model.keys[player];
        // A key drives one button per player: the old owner gets this button's key.
        for (const o in keys) if (o !== k && name !== 'None' && keys[o] === name) keys[o] = keys[k];
        keys[k] = name;
        cancelCapture();
      };
      window.addEventListener('keydown', onKey, true);
      capture = { stop: () => window.removeEventListener('keydown', onKey, true) };
    };
    return b;
  }
  function padButton(k) {
    const i = PAD_ORDER.indexOf(k);
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'bind';
    b.textContent = PAD_LABEL[model.pads[player][i]] || model.pads[player][i];
    b.onclick = () => {
      cancelCapture();
      b.textContent = 'Press a button…';
      b.classList.add('listening');
      const held = new Set();
      const pads = () => Array.from(navigator.getGamepads ? navigator.getGamepads() : []).filter(Boolean);
      for (const g of pads()) g.buttons.forEach((x, j) => x.pressed && held.add(g.index + ':' + j));
      let raf, stopped = false;
      const poll = () => {
        if (stopped) return;
        for (const g of pads()) {
          for (let j = 0; j < g.buttons.length && j < STD_PAD.length; j++) {
            if (!g.buttons[j].pressed || held.has(g.index + ':' + j)) continue;
            const name = STD_PAD[j], list = model.pads[player];
            const o = list.indexOf(name);
            if (o >= 0 && o !== i) list[o] = list[i];
            list[i] = name;
            return cancelCapture();
          }
        }
        raf = requestAnimationFrame(poll);
      };
      const onKey = (e) => { if (e.code === 'Escape') { e.preventDefault(); e.stopImmediatePropagation(); cancelCapture(); } };
      window.addEventListener('keydown', onKey, true);
      if (!pads().length) b.textContent = 'Connect a gamepad and press a button…';
      poll();
      capture = { stop: () => { stopped = true; cancelAnimationFrame(raf); window.removeEventListener('keydown', onKey, true); } };
    };
    return b;
  }

  function render() {
    for (const t of document.querySelectorAll('#set-players button')) t.classList.toggle('on', +t.dataset.p === player);
    $('set-src').value = model.src[player];
    $('set-src-note').hidden = model.src[player] !== 2;
    const grid = $('set-binds');
    grid.replaceChildren();
    for (const [k, label] of BUTTONS) {
      const row = document.createElement('div');
      row.className = 'bindrow';
      const l = document.createElement('span');
      l.textContent = label;
      row.append(l, keyButton(k), padButton(k));
      grid.append(row);
    }
    const hk = Object.entries(model.hotkeys).filter(([k]) => !/^f([1-9]|10)$/.test(k));
    $('set-hotkeys').textContent = hk.map(([k, v]) => `${v}: ${k[0].toUpperCase() + k.slice(1)}`).join(' · ') +
      ' · Load / save state: F1–F10 / Shift+F1–F10';
    $('set-aspect').value = model.aspect;
    $('set-linear').checked = model.linear;
    $('set-blend').checked = model.blend;
    $('set-sprites').checked = model.sprites;
    $('set-size').value = model.size;
    $('set-fps').checked = model.fps;
    $('set-audio').checked = model.audio;
    $('set-volume').value = model.volume;
    $('set-volume-v').textContent = model.volume + '%';
    let size = 0;
    try { size = FS.stat(SRAM).size; } catch (e) {}
    $('set-sram-info').textContent = size ? `Battery save: ${size} bytes (records, league progress, rider names).`
                                          : 'No battery save yet: it appears after you first play.';
    $('set-sram-down').disabled = $('set-sram-del').disabled = !size;
  }

  function tab(name) {
    for (const t of document.querySelectorAll('#set-tabs button')) t.classList.toggle('on', t.dataset.tab === name);
    for (const p of document.querySelectorAll('.set-pane')) p.hidden = p.dataset.tab !== name;
  }

  function init({ canvas, running, onSaved, onForgetRom, hasRom }) {
    const d = $('settings');
    for (const t of document.querySelectorAll('#set-tabs button')) t.onclick = () => tab(t.dataset.tab);
    for (const t of document.querySelectorAll('#set-players button')) t.onclick = () => { cancelCapture(); player = +t.dataset.p; render(); };
    $('set-src').onchange = (e) => {
      model.src[player] = +e.target.value;
      $('set-src-note').hidden = model.src[player] !== 2;
      // Two players on one keyboard need two sets of keys.
      const [k1, k2] = model.keys;
      if (player === 1 && model.src[1] === 1 && BUTTONS.every(([k]) => k2[k] === k1[k] || k2[k] === KEY_DEFAULTS[k])) {
        Object.assign(k2, KEY_P2);
        render();
      }
    };
    $('set-reset-binds').onclick = () => {
      Object.assign(model.keys[player], player === 1 && model.src[1] === 1 ? KEY_P2 : KEY_DEFAULTS);
      model.pads[player] = PAD_DEFAULTS.slice();
      render();
    };
    $('set-aspect').onchange = (e) => { model.aspect = e.target.value; };
    $('set-linear').onchange = (e) => { model.linear = e.target.checked; };
    $('set-blend').onchange = (e) => { model.blend = e.target.checked; };
    $('set-sprites').onchange = (e) => { model.sprites = e.target.checked; };
    $('set-size').onchange = (e) => { model.size = e.target.value; };
    $('set-fps').onchange = (e) => { model.fps = e.target.checked; };
    $('set-audio').onchange = (e) => { model.audio = e.target.checked; };
    $('set-volume').oninput = (e) => { model.volume = +e.target.value; $('set-volume-v').textContent = model.volume + '%'; };

    $('set-sram-down').onclick = () => {
      let data;
      try { data = FS.readFile(SRAM); } catch (e) { return; }
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([data]));
      a.download = 'Uniracers (USA).srm';
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    };
    $('set-sram-up').onchange = async (e) => {
      const f = e.target.files[0];
      e.target.value = '';
      if (!f) return;
      if (!f.size || f.size > 0x20000) { alert('That does not look like a SNES battery save.'); return; }
      if (!confirm('Replace this browser’s save with ' + f.name + '?')) return;
      FS.mkdirTree('/persist/saves');
      FS.writeFile(SRAM, new Uint8Array(await f.arrayBuffer()));
      FS.syncfs(false, () => {});
      render();
      onSaved(true);
    };
    $('set-sram-del').onclick = () => {
      if (!confirm('Delete the battery save (records, league progress, rider names)? This cannot be undone.')) return;
      try { FS.unlink(SRAM); } catch (e) {}
      FS.syncfs(false, () => {});
      render();
      onSaved(true);
    };
    $('set-forget').onclick = () => { onForgetRom(); $('set-forget').disabled = true; };
    $('set-reset-all').onclick = () => {
      if (!confirm('Reset every setting and control to the defaults? Saves are kept.')) return;
      for (const p of [CFG, KEYS]) try { FS.unlink(p); } catch (e) {}
      try { localStorage.removeItem('uni.size'); localStorage.removeItem('uni.fps'); } catch (e) {}
      model = load();
      applyPage(model, canvas);
      FS.syncfs(false, () => {});
      render();
      onSaved(true);
    };

    $('set-cancel').onclick = () => d.close();
    d.addEventListener('close', cancelCapture);
    $('set-save').onclick = () => {
      cancelCapture();
      save(model);
      applyPage(model, canvas);
      FS.syncfs(false, () => {});
      d.close();
      onSaved(running());
    };

    model = load();
    applyPage(model, canvas);
    return {
      open() {
        model = load();
        player = 0;
        $('set-forget').disabled = !hasRom();
        render();
        tab('controls');
        d.showModal();
      },
      showFps: () => model.fps,
    };
  }

  return { init, iniGet, iniSet, sdlKeyName };
})();
