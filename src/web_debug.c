/* Web-only diagnostics for the page's ?debug overlay (web/index.html).
 * Reads the host's audio counters; the page polls web_debug_stat(i). */
#include <emscripten.h>
#include "audio_trace.h"

extern double g_web_loop_stats[4];  /* host_main.c */

EMSCRIPTEN_KEEPALIVE double web_debug_stat(int i) {
  AudioTraceStats s;
  audio_trace_get_stats(&s);
  switch (i) {
  case 0: return (double)s.output_underflows;     /* starvation episodes */
  case 1: return (double)s.output_missing_frames; /* output frames of silence */
  case 2: return (double)s.dropped;               /* samples lost to overflow */
  case 3: return (double)s.occupancy_current;     /* queued native samples */
  case 4: return (double)s.produced;
  case 5: return (double)s.consumed;
  case 6: case 7: case 8: case 9: return g_web_loop_stats[i - 6];
  }
  return 0;
}
