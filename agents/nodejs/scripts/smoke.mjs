import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const provider = process.env.ZETATECH_PROVIDER || 'anthropic';
const model = process.env.ZETATECH_MODEL || '';
const key = process.env.ZETATECH_API_KEY || '';
const url = process.env.ZETATECH_BASE_URL || '';
const workspace = process.env.ZETATECH_WORKSPACE || process.cwd();

if (!model || !key) {
  console.error('Skipping smoke test: ZETATECH_MODEL and ZETATECH_API_KEY are required.');
  process.exit(0);
}

const runner = path.resolve('dist/index.js');
if (!fs.existsSync(runner)) {
  console.error(`Runner build missing at ${runner}. Run npm run build first.`);
  process.exit(1);
}

const payload = {
  workspaceRoot: workspace,
  prompt: 'Analyze this WordPress codebase and summarize functionality plus the most important security considerations.',
  model,
  provider,
  apiKey: key,
  ...(url ? { baseUrl: url } : {}),
  maxTurns: 6,
  maxTokens: 4000,
  temperature: 0.1,
};

const result = spawnSync('node', [runner], {
  input: JSON.stringify(payload),
  encoding: 'utf8',
  maxBuffer: 1024 * 1024 * 10,
});

if (result.status !== 0) {
  console.error(result.stderr || result.stdout || 'Smoke test failed.');
  process.exit(result.status ?? 1);
}

const lines = (result.stdout || '').trim().split('\n').filter(Boolean);
const events = lines.map((line) => JSON.parse(line));
const completed = events.find((event) => event.type === 'run_completed');
if (!completed?.data?.content) {
  console.error('Smoke test failed: run completed event missing content.');
  process.exit(1);
}

console.log('Smoke test passed.');
console.log(`Events: ${events.length}`);
console.log(`Output preview: ${String(completed.data.content).slice(0, 500)}`);
