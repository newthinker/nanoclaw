/**
 * Selvage client tool (Loom Plan 1).
 *
 * Writes a request into the mounted session mailbox and blocks-polls for the
 * host Selvage dispatcher's response. No network — rides the RW session-folder
 * mount at /workspace/selvage (= host data/v2-sessions/<ag>/<sess>/selvage).
 *
 * Authorization is enforced HOST-side by the dispatcher's per-group whitelist
 * (derived from the request file path). This tool is universally callable; a
 * group not whitelisted for the requested action prefix receives DENIED.
 *
 * IPC contract v1: req {id, action, params} → resp {id, status, result},
 * status ∈ OK | DENIED | ERROR. Request id matches ^[A-Za-z0-9._-]+$ so the
 * dispatcher's resp.ID sanitization accepts it.
 */
import { mkdirSync, writeFileSync, existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { registerTools } from './server.js';
import type { McpToolDefinition } from './types.js';

const MAILBOX = '/workspace/selvage';
const POLL_INTERVAL_MS = 100;
const MAX_POLLS = 80; // ~8s

function ok(text: string) {
  return { content: [{ type: 'text' as const, text }] };
}

function err(text: string) {
  return { content: [{ type: 'text' as const, text: `Error: ${text}` }], isError: true };
}

export const selvageCall: McpToolDefinition = {
  tool: {
    name: 'selvage_call',
    description:
      '经 Selvage 让宿主执行一个白名单 action(如 spool.archive 把合规笔记归档回 vault)。' +
      '返回宿主 dispatcher 的响应 JSON {id,status,result},status ∈ OK|DENIED|ERROR。' +
      '拿到 DENIED/ERROR 时如实告知用户,不要重试越权调用。',
    inputSchema: {
      type: 'object' as const,
      properties: {
        action: {
          type: 'string',
          description: '白名单 action,形如 "spool.archive"。',
        },
        params: {
          type: 'object',
          description:
            '该 action 的参数对象。例如 spool.archive: {path(vault 内相对路径), content(含 YAML frontmatter), mode("create"|"update")}。',
        },
      },
      required: ['action'],
    },
  },
  async handler(args) {
    const action = args.action as string;
    if (!action) return err('action is required');
    const params = (args.params as Record<string, unknown> | undefined) ?? {};

    const id = `c-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    try {
      mkdirSync(join(MAILBOX, 'req'), { recursive: true });
      writeFileSync(join(MAILBOX, 'req', `${id}.json`), JSON.stringify({ id, action, params }));
    } catch (e) {
      return err(`failed to write selvage request: ${e instanceof Error ? e.message : String(e)}`);
    }

    const respPath = join(MAILBOX, 'resp', `${id}.json`);
    for (let i = 0; i < MAX_POLLS; i++) {
      if (existsSync(respPath)) {
        try {
          return ok(readFileSync(respPath, 'utf8'));
        } catch (e) {
          return err(`failed to read selvage response: ${e instanceof Error ? e.message : String(e)}`);
        }
      }
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
    return err('no response from selvage dispatcher in 8s (is the host dispatcher running?)');
  },
};

registerTools([selvageCall]);
