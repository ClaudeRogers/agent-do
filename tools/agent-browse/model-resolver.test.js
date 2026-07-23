import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
    create: vi.fn(),
}));

vi.mock('@anthropic-ai/sdk', () => ({
    default: class FakeAnthropic {
        constructor() {
            this.messages = { create: mocks.create };
        }
    },
}));

import { callModel } from './model-resolver.js';

describe('provider-aware browser model calls', () => {
    let isolatedHome;

    beforeEach(() => {
        isolatedHome = mkdtempSync(path.join(tmpdir(), 'agent-do-model-test-'));
        process.env.AGENT_DO_HOME = isolatedHome;
        process.env.ANTHROPIC_API_KEY = 'fake-anthropic';
        process.env.OPENAI_API_KEY = 'fake-openai';
        mocks.create.mockReset();
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        rmSync(isolatedHome, { recursive: true, force: true });
    });

    it('crosses to the OpenAI Responses API only after model-not-found', async () => {
        mocks.create.mockRejectedValue(Object.assign(new Error('missing'), { status: 404 }));
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => ({
                output: [{ content: [{ type: 'output_text', text: 'ok' }] }],
            }),
        });
        vi.stubGlobal('fetch', fetchMock);

        const response = await callModel('vision', {
            max_tokens: 32,
            messages: [{ role: 'user', content: 'Reply ok' }],
        });

        expect(response.provider).toBe('openai');
        expect(response.model).toBe('gpt-5.6-terra');
        expect(response.text).toBe('ok');
        const body = JSON.parse(fetchMock.mock.calls[0][1].body);
        expect(body.reasoning).toEqual({ effort: 'medium' });
        expect(body.max_output_tokens).toBe(32);
    });
});
