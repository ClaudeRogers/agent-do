import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const moduleDir = path.dirname(fileURLToPath(import.meta.url));
const localAgentDo = path.resolve(moduleDir, '..', '..', 'agent-do');
const cache = new Map();

export function resolveModel(role = 'vision') {
    if (cache.has(role)) return cache.get(role);
    const executable = process.env.AGENT_DO_BIN || localAgentDo;
    const raw = execFileSync(executable, ['models', 'resolve', role, '--json'], {
        encoding: 'utf8',
        env: process.env,
    });
    const resolved = JSON.parse(raw);
    if (!resolved.model || resolved.provider !== 'anthropic') {
        throw new Error(`agent-browse requires an Anthropic ${role} model in this release`);
    }
    cache.set(role, resolved);
    return resolved;
}
