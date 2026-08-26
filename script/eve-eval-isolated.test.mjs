import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  writeFile,
} from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  acquireLock,
  archiveOwnedRunWorkflowStore,
  archiveWorkflowStore,
  isCompetingEveCommand,
  releaseLock,
  signalNumber,
} from '../bin/eve-eval-isolated';

const SCRIPT_PATH = fileURLToPath(new URL('../bin/eve-eval-isolated', import.meta.url));

test('archiveWorkflowStore isola o store sem apagar evidência', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'eve-isolated-eval-'));
  try {
    const workflowFile = path.join(root, '.eve', '.workflow-data', 'runs', 'wrun.json');
    const runRoot = path.join(root, '.eve', 'eval-isolated-runs', 'run-1');
    await mkdir(path.dirname(workflowFile), { recursive: true });
    await writeFile(workflowFile, '{"status":"running"}\n');

    const archived = await archiveWorkflowStore(
      root,
      runRoot,
      'preexisting-workflow-data',
    );

    assert.equal(archived, path.join(runRoot, 'preexisting-workflow-data'));
    await assert.rejects(readFile(workflowFile), { code: 'ENOENT' });
    assert.equal(await readFile(path.join(archived, 'runs', 'wrun.json'), 'utf8'), '{"status":"running"}\n');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('archiveOwnedRunWorkflowStore preserva store que o runner não possui', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'eve-isolated-owner-'));
  try {
    const workflowFile = path.join(root, '.eve', '.workflow-data', 'runs', 'active.json');
    const runRoot = path.join(root, '.eve', 'eval-isolated-runs', 'blocked-run');
    await mkdir(path.dirname(workflowFile), { recursive: true });
    await writeFile(workflowFile, '{"status":"running"}\n');

    assert.equal(await archiveOwnedRunWorkflowStore(root, runRoot, false), null);
    assert.equal(await readFile(workflowFile, 'utf8'), '{"status":"running"}\n');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('reconhece comandos Eve executados por nome, caminho local ou binário JavaScript', () => {
  assert.equal(isCompetingEveCommand('eve eval --filter smoke'), true);
  assert.equal(isCompetingEveCommand('./node_modules/.bin/eve eval'), true);
  assert.equal(isCompetingEveCommand('/repo/node_modules/eve/bin/eve.js dev'), true);
  assert.equal(isCompetingEveCommand('node unrelated-eve eval'), false);
});

test('preserva números de sinais além de interrupção e término', () => {
  assert.equal(signalNumber('SIGINT'), 2);
  assert.equal(signalNumber('SIGTERM'), 15);
  assert.equal(signalNumber('SIGKILL'), 9);
  assert.equal(signalNumber('SIGABRT'), 6);
});

test('lock ativo impede a bateria e preserva o store existente', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'eve-isolated-lock-'));
  let lock;
  try {
    const fakeEve = path.join(root, 'node_modules', '.bin', 'eve');
    const workflowFile = path.join(root, '.eve', '.workflow-data', 'runs', 'active.json');
    await mkdir(path.dirname(fakeEve), { recursive: true });
    await mkdir(path.dirname(workflowFile), { recursive: true });
    await writeFile(fakeEve, '#!/usr/bin/env node\n');
    await chmod(fakeEve, 0o755);
    await writeFile(workflowFile, '{"status":"running"}\n');
    lock = await acquireLock(root);

    const result = spawnSync(process.execPath, [SCRIPT_PATH], {
      cwd: root,
      encoding: 'utf8',
    });

    assert.equal(result.status, 1);
    assert.match(result.stderr, /Já existe uma bateria isolada ativa neste projeto/u);
    assert.equal(await readFile(workflowFile, 'utf8'), '{"status":"running"}\n');
  } finally {
    if (lock) await releaseLock(lock);
    await rm(root, { recursive: true, force: true });
  }
});

test('runtime iniciado por node_modules/.bin impede rotação do store ativo', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'eve-isolated-competitor-'));
  let competitor;
  try {
    const fakeEve = path.join(root, 'node_modules', '.bin', 'eve');
    const workflowFile = path.join(root, '.eve', '.workflow-data', 'runs', 'active.json');
    await mkdir(path.dirname(fakeEve), { recursive: true });
    await mkdir(path.dirname(workflowFile), { recursive: true });
    await writeFile(fakeEve, '#!/usr/bin/env node\nsetInterval(() => {}, 1000);\n');
    await chmod(fakeEve, 0o755);
    await writeFile(workflowFile, '{"status":"running"}\n');
    competitor = spawn(fakeEve, ['eval'], { cwd: root, stdio: 'ignore' });
    await once(competitor, 'spawn');

    const result = spawnSync(process.execPath, [SCRIPT_PATH], {
      cwd: root,
      encoding: 'utf8',
    });

    assert.equal(result.status, 1);
    assert.match(result.stderr, /Outro runtime Eve está ativo/u);
    assert.equal(await readFile(workflowFile, 'utf8'), '{"status":"running"}\n');
  } finally {
    if (competitor && competitor.exitCode === null) {
      competitor.kill('SIGTERM');
      await once(competitor, 'exit');
    }
    await rm(root, { recursive: true, force: true });
  }
});

test('propaga o código de saída correspondente ao sinal real do Eve', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'eve-isolated-signal-'));
  try {
    const fakeEve = path.join(root, 'node_modules', '.bin', 'eve');
    await mkdir(path.dirname(fakeEve), { recursive: true });
    await writeFile(fakeEve, "#!/usr/bin/env node\nprocess.kill(process.pid, 'SIGKILL');\n");
    await chmod(fakeEve, 0o755);

    const result = spawnSync(process.execPath, [SCRIPT_PATH], {
      cwd: root,
      encoding: 'utf8',
    });

    assert.equal(result.status, 137, result.stderr);
    const runNames = await readdir(path.join(root, '.eve', 'eval-isolated-runs'));
    const metadata = JSON.parse(
      await readFile(
        path.join(root, '.eve', 'eval-isolated-runs', runNames[0], 'metadata.json'),
        'utf8',
      ),
    );
    assert.equal(metadata.signal, 'SIGKILL');
    assert.equal(metadata.exitCode, 137);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('executa eval novo, preserva cache e arquiva os dois stores', async () => {
  const root = await mkdtemp(path.join(tmpdir(), 'eve-isolated-e2e-'));
  try {
    const fakeEve = path.join(root, 'node_modules', '.bin', 'eve');
    const oldWorkflowFile = path.join(root, '.eve', '.workflow-data', 'runs', 'old.json');
    const cacheFile = path.join(root, '.eve', 'm', 'cache.txt');
    await mkdir(path.dirname(fakeEve), { recursive: true });
    await mkdir(path.dirname(oldWorkflowFile), { recursive: true });
    await mkdir(path.dirname(cacheFile), { recursive: true });
    await writeFile(oldWorkflowFile, '{"source":"old"}\n');
    await writeFile(cacheFile, 'preservar\n');
    await writeFile(
      fakeEve,
      `#!/usr/bin/env node
const { mkdirSync, writeFileSync } = require('node:fs');
const { join } = require('node:path');
const workflow = join(process.cwd(), '.eve', '.workflow-data', 'runs');
mkdirSync(workflow, { recursive: true });
writeFileSync(join(workflow, 'new.json'), '{"source":"new"}\\n');
writeFileSync(join(process.cwd(), 'observation.json'), JSON.stringify({
  args: process.argv.slice(2),
  bodyTimeout: process.env.WORKFLOW_LOCAL_BODY_TIMEOUT_MS,
  headersTimeout: process.env.WORKFLOW_LOCAL_HEADERS_TIMEOUT_MS,
  msbHome: process.env.MSB_HOME,
}));
process.exitCode = 7;
`,
    );
    await chmod(fakeEve, 0o755);

    const result = spawnSync(process.execPath, [SCRIPT_PATH, '--filter', 'smoke'], {
      cwd: root,
      encoding: 'utf8',
    });

    assert.equal(result.status, 7, result.stderr);
    assert.equal(await readFile(cacheFile, 'utf8'), 'preservar\n');
    await assert.rejects(readFile(oldWorkflowFile), { code: 'ENOENT' });
    const runNames = await readdir(path.join(root, '.eve', 'eval-isolated-runs'));
    assert.equal(runNames.length, 1);
    const runRoot = path.join(root, '.eve', 'eval-isolated-runs', runNames[0]);
    assert.equal(
      await readFile(path.join(runRoot, 'preexisting-workflow-data', 'runs', 'old.json'), 'utf8'),
      '{"source":"old"}\n',
    );
    assert.equal(
      await readFile(path.join(runRoot, 'run-workflow-data', 'runs', 'new.json'), 'utf8'),
      '{"source":"new"}\n',
    );
    const observation = JSON.parse(await readFile(path.join(root, 'observation.json'), 'utf8'));
    assert.deepEqual(observation, {
      args: ['eval', '--filter', 'smoke'],
      bodyTimeout: '300000',
      headersTimeout: '300000',
      msbHome: path.join(root, '.eve', 'm'),
    });
    const metadata = JSON.parse(await readFile(path.join(runRoot, 'metadata.json'), 'utf8'));
    assert.equal(metadata.exitCode, 7);
    assert.deepEqual(metadata.arguments, ['--filter', 'smoke']);
    assert.equal(metadata.timeZone, 'America/Sao_Paulo');
    assert.match(result.stderr, /Workflow store anterior arquivado/u);
    assert.match(result.stderr, /Estado isolado da bateria/u);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
