/* Online two-player for the web build: the lockstep half.
 *
 * A web-only addon (CMakeLists compiles it only under Emscripten): the
 * desktop recomp never links it. web/netplay.js owns the lobby and the
 * browser-to-browser data channel (WebRTC); this file keeps the two
 * emulators in step.
 *
 * Both players boot the same ROM with the same SRAM, so the machines stay
 * identical as long as every frame runs with the same pads. Each frame N
 * sends this side's pad for frame N + kDelay and runs N with both sides'
 * pads for N, waiting for the peer's if it has not arrived (the 3-frame
 * delay, 50 ms, hides the round trip). The host is pad 1, the guest pad 2.
 * Every 120 frames each side sends a CRC of WRAM; the page compares them,
 * so a desync is reported instead of silently diverging. */
#include <emscripten.h>
#include <stdint.h>

extern uint8_t g_ram[];

enum { kDelay = 3, kRing = 64, kCrcEvery = 120, kRamSize = 0x20000 };

/* 0 = off (solo), 1 = host, 2 = guest; set by the page before main(). */
EM_JS(int, web_net_role, (void), {
  return Module.webNet ? Module.webNet.role : 0;
});
EM_JS(void, web_net_send_pad, (unsigned frame, unsigned pad), {
  Module.webNet.sendPad(frame, pad);
});
EM_JS(void, web_net_send_crc, (unsigned frame, unsigned crc), {
  Module.webNet.sendCrc(frame, crc);
});
/* The peer's pad for `frame`, waiting for it; -1 once the peer has left. */
EM_ASYNC_JS(int, web_net_recv_pad, (unsigned frame), {
  return await Module.webNet.recvPad(frame);
});

static uint32_t Crc32(const uint8_t *p, unsigned n) {
  static uint32_t table[256];
  if (!table[1]) {
    for (uint32_t i = 0; i < 256; i++) {
      uint32_t c = i;
      for (int k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
      table[i] = c;
    }
  }
  uint32_t c = 0xFFFFFFFFu;
  while (n--) c = table[(c ^ *p++) & 0xFF] ^ (c >> 8);
  return ~c;
}

uint32_t WebNetplayFilterInputs(uint32_t word, unsigned frame) {
  static int role = -1, peer_gone;
  static uint16_t mine[kRing];
  if (role < 0) role = web_net_role();
  if (role == 0 || peer_gone) return word;

  uint16_t local = word & 0xFFF;          /* this player's pad, from pad-1 keys */
  mine[(frame + kDelay) % kRing] = local;
  web_net_send_pad(frame + kDelay, local);
  if (frame % kCrcEvery == 0) web_net_send_crc(frame, Crc32(g_ram, kRamSize));

  uint16_t me = frame < kDelay ? 0 : mine[frame % kRing], other = 0;
  if (frame >= kDelay) {
    int got = web_net_recv_pad(frame);
    if (got < 0) peer_gone = 1;           /* carry on alone: the page says so */
    else other = (uint16_t)got;
  }
  uint32_t p1 = role == 1 ? me : other, p2 = role == 1 ? other : me;
  return p1 | (p2 << 12) | (3u << 30);    /* both ports present */
}
