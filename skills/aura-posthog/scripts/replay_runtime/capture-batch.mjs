// Dataset compartilhado, páginas isoladas e concorrência limitada.
export async function captureJobs(jobs, { open, run, close, workers = 2 }) {
  if (!Number.isInteger(workers) || workers < 1 || workers > 2)
    throw new Error("Captura exige um ou dois workers.");
  const results = Array.from({ length: jobs.length });
  let next = 0;
  let failed = false;
  const worker = async () => {
    let browser;
    try {
      browser = await open();
      while (!failed && next < jobs.length) {
        const index = next++;
        results[index] = await run(browser, jobs[index]);
      }
    } catch (error) {
      failed = true;
      throw error;
    } finally {
      if (browser) await close(browser);
    }
  };
  // Esperar cleanup dos siblings antes de devolver uma falha.
  const settled = await Promise.allSettled(
    Array.from({ length: Math.min(workers, jobs.length) }, worker),
  );
  const failure = settled.find((result) => result.status === "rejected");
  if (failure) throw failure.reason;
  return results;
}
