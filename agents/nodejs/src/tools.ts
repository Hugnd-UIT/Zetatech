import { execFile } from 'node:child_process';
import path from 'node:path';
import { realpath } from 'node:fs/promises';
import { promisify } from 'node:util';

import {
  bashTool,
  defineTool,
  fileEditTool,
  fileReadTool,
  fileWriteTool,
  grepTool,
} from '@jackchen_me/open-multi-agent';
import type { ToolDefinition } from '@jackchen_me/open-multi-agent';
import { z } from 'zod';

const exec = promisify(execFile);

function resolvePath(raw: string, root: string): string {
  const text = String(raw ?? '').trim();
  if (!text) {
    return text;
  }

  const unix = text.replace(/\\/g, '/');
  if (unix === '/workspace') {
    return root;
  }
  if (unix.startsWith('/workspace/')) {
    return path.resolve(root, unix.slice('/workspace/'.length));
  }

  if (path.isAbsolute(text)) {
    return text;
  }

  return path.resolve(root, text);
}

function makeRead(root: string, name: 'read' | 'file_read'): ToolDefinition {
  return {
    ...fileReadTool,
    name,
    execute: async (input, context) => {
      const args = input as { path: string; offset?: number; limit?: number };
      const target = resolvePath(args.path, root);
      return fileReadTool.execute({ ...args, path: target }, context);
    },
  };
}

function makeWrite(root: string, name: 'write' | 'file_write'): ToolDefinition {
  return {
    ...fileWriteTool,
    name,
    execute: async (input, context) => {
      const args = input as { path: string; content: string };
      const target = resolvePath(args.path, root);
      return fileWriteTool.execute({ ...args, path: target }, context);
    },
  };
}

function makeEdit(root: string, name: 'edit' | 'file_edit'): ToolDefinition {
  return {
    ...fileEditTool,
    name,
    execute: async (input, context) => {
      const args = input as {
        path: string;
        old_string?: string;
        new_string?: string;
        oldText?: string;
        newText?: string;
        replace_all?: boolean;
      };

      const oldText = args.old_string ?? args.oldText;
      const newText = args.new_string ?? args.newText;
      if (typeof oldText !== 'string' || typeof newText !== 'string') {
        throw new Error('edit requires old_string/new_string or oldText/newText');
      }

      const target = resolvePath(args.path, root);
      return fileEditTool.execute(
        {
          ...args,
          path: target,
          old_string: oldText,
          new_string: newText,
          replace_all: args.replace_all,
        },
        context,
      );
    },
  };
}

function makeGrep(root: string): ToolDefinition {
  return {
    ...grepTool,
    execute: async (input, context) => {
      const args = input as { pattern: string; path?: string; glob?: string; maxResults?: number };
      const target = args.path ? resolvePath(args.path, root) : root;
      return grepTool.execute({ ...args, path: target }, context);
    },
  };
}

function makeBash(root: string): ToolDefinition {
  return {
    ...bashTool,
    execute: async (input, context) => {
      const args = input as { command: string; timeout?: number; timeoutMs?: number; cwd?: string };
      const cwd = args.cwd ? resolvePath(args.cwd, root) : root;
      const timeout = args.timeoutMs ?? args.timeout;
      return bashTool.execute(
        {
          command: args.command,
          timeout,
          cwd,
        },
        context,
      );
    },
  };
}

function formatError(err: unknown): string {
  if (err && typeof err === 'object') {
    const obj = err as { stdout?: string | Buffer; stderr?: string | Buffer; message?: string };
    const stdout = obj.stdout ? obj.stdout.toString() : '';
    const stderr = obj.stderr ? obj.stderr.toString() : '';
    const text = [stdout, stderr].filter(Boolean).join('');
    return text || obj.message || 'command failed';
  }
  return String(err || 'command failed');
}

async function semgrep(config: string, root: string): Promise<string> {
  const cwd = await realpath(root).catch(() => root);

  try {
    const { stdout, stderr } = await exec('semgrep', ['--config', config, '--json', '.'], {
      cwd,
      timeout: 120000,
      maxBuffer: 10 * 1024 * 1024,
    });

    return [stdout, stderr].filter(Boolean).join('') || '(no output)';
  } catch (err) {
    throw new Error(formatError(err));
  }
}

function compactSemgrepOutput(raw: string): string {
  const MAX_CHARS = 16000;
  try {
    const parsed = JSON.parse(raw) as {
      results?: Array<{
        check_id?: string;
        path?: string;
        start?: { line?: number };
        extra?: { severity?: string; message?: string; lines?: string };
      }>;
      errors?: unknown[];
    };
    if (parsed && Array.isArray(parsed.results)) {
      const findings = parsed.results.slice(0, 40).map((r) => ({
        rule: r.check_id || '',
        file: r.path || '',
        line: r.start?.line ?? 0,
        severity: r.extra?.severity || '',
        message: String(r.extra?.message || '').slice(0, 240),
        snippet: String(r.extra?.lines || '').slice(0, 200),
      }));
      const summary = JSON.stringify({
        total_results: parsed.results.length,
        truncated: parsed.results.length > 40,
        showing: findings.length,
        findings,
      });
      return summary.length > MAX_CHARS ? summary.slice(0, MAX_CHARS) + '...[truncated]' : summary;
    }
  } catch {
    // Fall back to plain text truncation when output is not JSON.
  }
  return raw.length > MAX_CHARS ? raw.slice(0, MAX_CHARS) + '\n...[truncated]' : raw;
}

function makeSemgrep(root: string): ToolDefinition {
  return defineTool({
    name: 'run_semgrep',
    description: 'Run semgrep inside the workspace and return compact JSON findings.',
    inputSchema: z.object({
      config: z.string().min(1).default('auto'),
    }),
    execute: async ({ config }) => {
      const output = await semgrep(config ?? 'auto', root);
      return { data: compactSemgrepOutput(output) };
    },
  });
}

export function buildTools(root: string): ToolDefinition[] {
  return [
    makeRead(root, 'read'),
    makeRead(root, 'file_read'),
    makeWrite(root, 'write'),
    makeWrite(root, 'file_write'),
    makeEdit(root, 'edit'),
    makeEdit(root, 'file_edit'),
    makeGrep(root),
    makeBash(root),
    makeSemgrep(root),
  ];
}
