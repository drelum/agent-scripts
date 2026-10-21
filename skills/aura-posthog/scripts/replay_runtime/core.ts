import { readFileSync, writeFileSync } from "node:fs";
import {
  parseJsonSnapshots,
  createWindowIdRegistry,
  processAllSnapshots,
  keyForSource,
  SnapshotSourceType,
  SnapshotStore,
  createSegments,
  mapSnapshotsToWindowId,
  clearThrottle,
} from "@posthog/replay-shared";
import type { RecordingSnapshot, ReplayTelemetry } from "@posthog/replay-shared";
import { planNextBatch } from "./vendor/posthog/planNextBatch";

export async function prepare(text: string) {
  clearThrottle(); // Cada preparação precisa observar seus próprios erros, sem supressão entre sessões.
  const diagnostics: Record<string, number> = {};
  let invalid = false;
  const telemetry: ReplayTelemetry = {
    captureException: () => {
      invalid = true;
      diagnostics.decode_errors = (diagnostics.decode_errors || 0) + 1;
    },
    capture: (name) => {
      diagnostics[name] = (diagnostics[name] || 0) + 1;
      if (name === "session recording had unparseable lines") invalid = true;
    },
  };
  const started = performance.now();
  const registry = createWindowIdRegistry();
  const window_id_map: Record<string, number> = {};
  // O parser upstream pode reintroduzir windowId cru ao espalhar um evento flat.
  // Converter esse formato para o envelope antes de registrar a aba; fontes vendorizadas intactas.
  const lines = text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => {
      const row: unknown = JSON.parse(line);
      if (
        row &&
        typeof row === "object" &&
        "type" in row &&
        "timestamp" in row &&
        "windowId" in row &&
        typeof row.windowId === "string"
      ) {
        const { windowId, ...event } = row;
        return JSON.stringify([windowId, event]);
      }
      return line;
    });
  const snapshots = parseJsonSnapshots(lines, "local-lab", telemetry, (id) => {
    const mapped = registry(id);
    window_id_map[id] = mapped;
    return mapped;
  });
  const source = { source: SnapshotSourceType.blob_v2, blob_key: "0" };
  const events = await processAllSnapshots(
    [source],
    { [keyForSource(source)]: { snapshots, sourceLoaded: true } },
    { snapshots: {} },
    () => undefined,
    "local-lab",
    telemetry,
  );
  if (
    invalid ||
    !events.length ||
    events.some((e) => !Number.isFinite(e.timestamp) || !e.windowId)
  ) {
    throw new Error("Eventos inválidos ou incompletos; nenhuma sessão preparada.");
  }
  return { events, diagnostics, window_id_map, preparation_ms: performance.now() - started };
}

export function segment(events: RecordingSnapshot[]) {
  return createSegments(
    events,
    events[0].timestamp,
    events.at(-1)!.timestamp,
    undefined,
    mapSnapshotsToWindowId(events),
  );
}

// Experimento independente de carregamento: mesmos eventos, fontes locais de até 100 eventos.
export function planExperiment(events: RecordingSnapshot[], timestamp: number, windowId: number) {
  const groups: RecordingSnapshot[][] = [];
  for (let i = 0; i < events.length; i += 100) groups.push(events.slice(i, i + 100));
  const store = new SnapshotStore();
  store.setSources(
    groups.map((g, i) => ({
      source: SnapshotSourceType.blob_v2,
      blob_key: String(i),
      start_timestamp: new Date(g[0].timestamp).toISOString(),
      end_timestamp: new Date(g.at(-1)!.timestamp).toISOString(),
    })),
  );
  const batches = [];
  while (!store.canPlayAt(timestamp, windowId)) {
    const batch = planNextBatch(store, { target: { timestamp, windowId }, loadAll: false }, 2);
    if (!batch) break;
    batches.push(batch);
    batch.sourceIndices.forEach((i) => store.markFetched(i, [...groups[i]]));
    store.markProcessed(batch.sourceIndices);
    if (batches.length > groups.length) throw new Error("Planejador não convergiu.");
  }
  return {
    playable: store.canPlayAt(timestamp, windowId),
    total_sources: groups.length,
    loaded_sources: groups.filter((_, i) => store.getEntry(i)?.state === "loaded").length,
    batches,
  };
}

if (require.main === module) {
  (async () => {
    if (process.argv[2] === "plan") {
      const windows: Record<string, RecordingSnapshot[]> = JSON.parse(
        readFileSync(process.argv[3], "utf8"),
      );
      const events = Object.entries(windows)
        .flatMap(([windowId, values]) => values.map((e) => ({ ...e, windowId: Number(windowId) })))
        .sort((a, b) => a.timestamp - b.timestamp);
      console.log(
        JSON.stringify(planExperiment(events, Number(process.argv[4]), Number(process.argv[5]))),
      );
      return;
    }
    const result = await prepare(readFileSync(process.argv[2], "utf8"));
    writeFileSync(
      process.argv[3],
      JSON.stringify({ ...result, segments: segment(result.events) }),
      { mode: 0o600 },
    );
    console.log(
      JSON.stringify({
        events: result.events.length,
        diagnostics: result.diagnostics,
        preparation_ms: result.preparation_ms,
      }),
    );
  })().catch(() => {
    console.error("Preparação upstream recusada: erro de formato/codec; payload omitido.");
    process.exitCode = 1;
  });
}
