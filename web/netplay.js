// Online two-player lobby and transport for the web build.
//
// The host creates a lobby: its PeerJS id is "uniracers-<code>", so the code
// is all a friend needs. The guest connects to that id; PeerJS's public
// broker only introduces the two browsers, the game then talks over a direct
// WebRTC data channel (reliable, ordered). Before the game starts the two
// sides check they loaded the same ROM and the host sends its battery save,
// so both emulators boot identical. src/web_netplay.c runs the lockstep
// through the Module.webNet object built here.
'use strict';

const UniNet = (() => {
  const PREFIX = 'uniracers-';
  const ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';  // no 0/O, 1/I/L

  const newCode = () => Array.from(crypto.getRandomValues(new Uint8Array(6)),
                                   (b) => ALPHABET[b % ALPHABET.length]).join('');

  // The lockstep side of a connected data channel.
  function session(conn, role, events) {
    const pads = new Map(), waiting = new Map(), crcs = new Map();
    let closed = false;
    const settle = (frame, value) => {
      const w = waiting.get(frame);
      if (w) { waiting.delete(frame); w(value); return true; }
      return false;
    };
    conn.on('data', (msg) => {
      if (!Array.isArray(msg)) return;
      if (msg[0] === 'p') { if (!settle(msg[1], msg[2])) pads.set(msg[1], msg[2]); }
      else if (msg[0] === 'c') checkCrc(msg[1], msg[2], 'remote');
    });
    const close = (why) => {
      if (closed) return;
      closed = true;
      for (const w of waiting.values()) w(-1);
      waiting.clear();
      events.onLeft(why);
    };
    conn.on('close', () => close('Your opponent left.'));
    conn.on('error', (e) => close('Connection lost: ' + e));

    function checkCrc(frame, crc, from) {
      const other = crcs.get(frame);
      if (other === undefined) { crcs.set(frame, { [from]: crc }); return; }
      if (other[from] !== undefined) return;
      crcs.delete(frame);
      const mine = from === 'local' ? crc : other.local, theirs = from === 'remote' ? crc : other.remote;
      if (mine !== theirs) events.onDesync(frame);
    }

    return {
      role,
      sendPad(frame, pad) { if (!closed) conn.send(['p', frame, pad]); },
      sendCrc(frame, crc) { if (!closed) conn.send(['c', frame, crc]); checkCrc(frame, crc, 'local'); },
      recvPad(frame) {
        if (pads.has(frame)) { const v = pads.get(frame); pads.delete(frame); return v; }
        if (closed) return -1;
        events.onWait(true);
        return new Promise((resolve) => waiting.set(frame, (v) => { events.onWait(false); resolve(v); }));
      },
    };
  }

  // Host: open a lobby, wait for one guest with the same ROM.
  function host({ romHash, sram, onCode, onReady, onError, events }) {
    const code = newCode();
    const peer = new Peer(PREFIX + code);
    peer.on('open', () => onCode(code));
    peer.on('error', (e) => onError(e.type === 'unavailable-id' ? 'Code clash, try again.' : String(e)));
    peer.on('connection', (conn) => {
      conn.on('data', function hello(msg) {
        if (!Array.isArray(msg) || msg[0] !== 'hello') return;
        conn.off('data', hello);
        if (msg[1] !== romHash) {
          conn.send(['bye', 'The host has a different ROM.']);
          setTimeout(() => conn.close(), 500);
          return;
        }
        conn.send(['start', sram]);
        peer.disconnect();  // the lobby is full: stop taking connections
        onReady(session(conn, 1, events));
      });
    });
    return () => peer.destroy();
  }

  // Guest: join a lobby by code.
  function join({ code, romHash, onReady, onError, events }) {
    const peer = new Peer();
    peer.on('error', (e) => onError(e.type === 'peer-unavailable' ? 'No lobby with that code.' : String(e)));
    peer.on('open', () => {
      const conn = peer.connect(PREFIX + code.trim().toUpperCase(), { reliable: true, serialization: 'json' });
      conn.on('open', () => conn.send(['hello', romHash]));
      conn.on('data', function start(msg) {
        if (!Array.isArray(msg)) return;
        if (msg[0] === 'bye') { onError(msg[1]); conn.close(); return; }
        if (msg[0] !== 'start') return;
        conn.off('data', start);
        onReady(session(conn, 2, events), msg[1]);
      });
    });
    return () => peer.destroy();
  }

  return { host, join };
})();
