import { test } from "node:test";
import assert from "node:assert/strict";
import { captureJobs } from "./capture-batch.mjs";

void test("dois browsers reutilizados; resultados mantêm ordem e concorrência limitada", async () => {
  let opened = 0;
  let active = 0;
  let peak = 0;
  const closed = [];
  const results = await captureJobs([0, 1, 2, 3], {
    open: async () => ++opened,
    run: async (_browser, job) => {
      active++;
      peak = Math.max(peak, active);
      await new Promise((resolve) => setTimeout(resolve, job === 0 ? 10 : 1));
      active--;
      return job;
    },
    close: async (browser) => closed.push(browser),
  });
  assert.deepEqual(results, [0, 1, 2, 3]);
  assert.equal(opened, 2);
  assert.equal(peak, 2);
  assert.deepEqual(
    closed.sort((a, b) => a - b),
    [1, 2],
  );
});

void test("falha interrompe fila e aguarda captura ativa e fechamento de ambos", async () => {
  const started = [];
  const closed = [];
  let opened = 0;
  let siblingDone = false;
  await assert.rejects(
    captureJobs([0, 1, 2, 3], {
      open: async () => ++opened,
      run: async (_browser, job) => {
        started.push(job);
        if (job === 0) throw new Error("captura falhou");
        await new Promise((resolve) => setTimeout(resolve, 10));
        siblingDone = true;
      },
      close: async (browser) => closed.push(browser),
    }),
    /captura falhou/,
  );
  assert.deepEqual(started, [0, 1]);
  assert.equal(siblingDone, true);
  assert.deepEqual(
    closed.sort((a, b) => a - b),
    [1, 2],
  );
});

void test("falha ao abrir browser ainda fecha sibling; limite não pode ser ampliado", async () => {
  let opened = 0;
  let closed = 0;
  await assert.rejects(
    captureJobs([0, 1], {
      open: async () => {
        if (++opened === 1) throw new Error("launch");
        return {};
      },
      run: async () => {},
      close: async () => closed++,
    }),
    /launch/,
  );
  assert.equal(closed, 1);
  await assert.rejects(captureJobs([0], { workers: 3 }), /workers/);
});
