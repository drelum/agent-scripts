import assert from 'node:assert/strict';
import test from 'node:test';
import {
  parseDeploymentInspection,
  parseRemoteProductionOptions,
} from '../bin/eve-eval-remote-production';

test('separa configuração global do comando específico e preserva o -- do pnpm', () => {
  assert.deepEqual(
    parseRemoteProductionOptions([
      '--audience',
      'urn:aitrus:service:agent',
      '--',
      'pnpm',
      'experiment:remote:runtime',
      '--',
      '--url',
      'https://agent.vercel.app',
      '--repetitions',
      '10',
    ]),
    {
      audience: 'urn:aitrus:service:agent',
      command: [
        'pnpm',
        'experiment:remote:runtime',
        '--',
        '--url',
        'https://agent.vercel.app',
        '--repetitions',
        '10',
      ],
      targetUrl: 'https://agent.vercel.app/',
    },
  );
});

test('recusa alvo sem HTTPS ou sem URL inequívoca', () => {
  assert.throws(
    () => parseRemoteProductionOptions(['--audience', 'aud', '--', 'eve', 'eval']),
    /exatamente uma opção --url/,
  );
  assert.throws(
    () =>
      parseRemoteProductionOptions([
        '--audience',
        'aud',
        '--',
        'eve',
        'eval',
        '--url',
        'http://agent.example',
      ]),
    /HTTPS/,
  );
});

test('aceita somente deployment Production READY da Vercel', () => {
  assert.deepEqual(
    parseDeploymentInspection(
      `${JSON.stringify({
        createdAt: 1_787_785_301_635,
        id: 'dpl_123',
        name: 'agent',
        readyState: 'READY',
        target: 'production',
        url: 'agent-hash.vercel.app',
      })}\n`,
    ),
    {
      createdAt: '2026-08-26T23:01:41.635Z',
      id: 'dpl_123',
      name: 'agent',
      readyState: 'READY',
      target: 'production',
      url: 'https://agent-hash.vercel.app',
    },
  );
  assert.throws(
    () =>
      parseDeploymentInspection(
        JSON.stringify({
          id: 'dpl_preview',
          name: 'agent',
          readyState: 'READY',
          target: null,
          url: 'agent-preview.vercel.app',
        }),
      ),
    /Production/,
  );
  assert.throws(
    () =>
      parseDeploymentInspection(
        JSON.stringify({
          id: 'dpl_other',
          name: 'other-agent',
          readyState: 'READY',
          target: 'production',
          url: 'other-agent.vercel.app',
        }),
        'agent',
      ),
    /não ao projeto local/,
  );
});
