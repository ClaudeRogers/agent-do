import Anthropic from '@anthropic-ai/sdk';
import { execFileSync, spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const moduleDir = path.dirname(fileURLToPath(import.meta.url));
const localAgentDo = path.resolve(moduleDir, '..', '..', 'agent-do');
const cache = new Map();
let anthropicClient = null;

export function resolveModel(role = 'vision') {
    if (cache.has(role)) return cache.get(role);
    const executable = process.env.AGENT_DO_BIN || localAgentDo;
    const raw = execFileSync(executable, ['models', 'resolve', role, '--json'], {
        encoding: 'utf8',
        env: process.env,
    });
    const resolved = JSON.parse(raw);
    if (!resolved.model || !resolved.provider) {
        throw new Error(`agent-browse could not resolve the ${role} model role`);
    }
    cache.set(role, resolved);
    return resolved;
}

function getAnthropicClient() {
    if (!anthropicClient) {
        anthropicClient = new Anthropic({ timeout: 30000, maxRetries: 2 });
    }
    return anthropicClient;
}

function openAIContent(content) {
    if (typeof content === 'string') return content;
    if (!Array.isArray(content)) return String(content || '');
    return content.map((item) => {
        if (item.type === 'text') return { type: 'input_text', text: item.text };
        if (item.type === 'image' && item.source?.type === 'base64') {
            return {
                type: 'input_image',
                image_url: `data:${item.source.media_type};base64,${item.source.data}`,
            };
        }
        return null;
    }).filter(Boolean);
}

async function fetchWithRetry(url, options) {
    let lastError;
    for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
            const response = await fetch(url, {
                ...options,
                signal: AbortSignal.timeout(30000),
            });
            if (![429, 500, 502, 503, 504].includes(response.status) || attempt === 2) {
                return response;
            }
            await response.text();
            lastError = new Error(`OpenAI transient HTTP ${response.status}`);
        } catch (error) {
            lastError = error;
            if (attempt === 2) throw error;
        }
        await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
    }
    throw lastError;
}

async function callOpenAI(candidate, request) {
    if (!process.env.OPENAI_API_KEY) {
        throw new Error('OPENAI_API_KEY is unavailable');
    }
    const generation = candidate.generation_params || candidate.capabilities?.generation || {};
    const body = {
        model: candidate.model,
        input: (request.messages || []).map((item) => ({
            role: item.role === 'system' ? 'developer' : item.role,
            content: openAIContent(item.content),
        })),
        max_output_tokens: request.max_tokens || 1024,
        store: false,
        ...generation,
    };
    const response = await fetchWithRetry('https://api.openai.com/v1/responses', {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
        const error = new Error(payload?.error?.message || `OpenAI HTTP ${response.status}`);
        error.status = response.status;
        throw error;
    }
    const text = (payload.output || [])
        .flatMap((item) => item.content || [])
        .filter((item) => item.type === 'output_text')
        .map((item) => item.text || '')
        .join('\n');
    return { text, provider: 'openai', model: candidate.model, raw: payload };
}

async function callAnthropic(candidate, request) {
    if (!process.env.ANTHROPIC_API_KEY) {
        throw new Error('ANTHROPIC_API_KEY is unavailable');
    }
    const generation = candidate.generation_params || candidate.capabilities?.generation || {};
    const response = await getAnthropicClient().messages.create({
        model: candidate.model,
        max_tokens: request.max_tokens || 1024,
        system: request.system,
        messages: request.messages || [],
        ...generation,
    });
    const text = (response.content || [])
        .filter((item) => item.type === 'text')
        .map((item) => item.text || '')
        .join('\n');
    return { text, provider: 'anthropic', model: candidate.model, raw: response };
}

function isModelNotFound(error) {
    return (error?.status ?? error?.statusCode) === 404;
}

function reportFallback(role, failed, selected) {
    process.stderr.write(
        `agent-do models: ${failed.provider}/${failed.model} was not found; `
        + `falling back to ${selected.provider}/${selected.model}\n`,
    );
    const code = [
        'import sys',
        'from pathlib import Path',
        'sys.path.insert(0, str(Path(sys.argv[1]) / "lib"))',
        'from telemetry import append_event',
        'append_event("model_fallback", "models", role=sys.argv[2], failed_provider=sys.argv[3], failed_model=sys.argv[4], selected_provider=sys.argv[5], selected_model=sys.argv[6])',
    ].join(';');
    spawnSync('python3', [
        '-c', code, path.resolve(moduleDir, '..', '..'), role,
        failed.provider, failed.model, selected.provider, selected.model,
    ], { stdio: 'ignore', env: process.env });
}

export async function callModel(role, request) {
    const resolved = resolveModel(role);
    const candidates = (resolved.candidates || [resolved]).filter((candidate) => (
        (candidate.provider === 'anthropic' && process.env.ANTHROPIC_API_KEY)
        || (candidate.provider === 'openai' && process.env.OPENAI_API_KEY)
    ));
    if (!candidates.length) {
        throw new Error(`No configured provider credential can serve model role '${role}'`);
    }
    let failed = null;
    let lastError = null;
    for (const candidate of candidates) {
        if (failed) {
            reportFallback(role, failed, candidate);
            failed = null;
        }
        try {
            if (candidate.provider === 'anthropic') return await callAnthropic(candidate, request);
            if (candidate.provider === 'openai') return await callOpenAI(candidate, request);
            throw new Error(`Unsupported model provider: ${candidate.provider}`);
        } catch (error) {
            if (!isModelNotFound(error)) throw error;
            failed = candidate;
            lastError = error;
        }
    }
    throw new Error(`Model chain exhausted for role '${role}'`, { cause: lastError });
}
