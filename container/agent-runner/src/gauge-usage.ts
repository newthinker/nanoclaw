// Gauge spike: append one JSONL line of token usage into the mounted session
// folder. /workspace/.gauge maps to host data/v2-sessions/<agid>/<sid>/.gauge,
// so the host reads it over the mount — no DB, no network.
import { appendFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

const GAUGE_DIR = '/workspace/.gauge';

export function appendUsage(entry: Record<string, unknown>): void {
  try {
    mkdirSync(GAUGE_DIR, { recursive: true });
    const line = JSON.stringify({ ts: new Date().toISOString(), ...entry }) + '\n';
    appendFileSync(join(GAUGE_DIR, 'usage.jsonl'), line);
  } catch (e) {
    console.error('[gauge] appendUsage failed:', e);
  }
}
