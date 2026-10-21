import { Replayer } from "posthog-js/rrweb";
import type { eventWithTime } from "posthog-js/rrweb-types";
import { COMMON_REPLAYER_CONFIG, speedDependentStyleRules } from "@posthog/replay-shared";
import { chooseWindow } from "./frame";

type Tab = {
  id: string;
  events: number;
  start: number;
  end: number;
  snapshots: number;
  clicks: number;
  input_updates: number;
};
type Evidence = {
  window: string;
  session_s: number;
  kind: string;
  control?: string;
  path?: string;
  state?: string;
};
type Manifest = {
  name: string;
  start: number;
  end: number;
  duration_s: number;
  windows: Tab[];
  evidence: Evidence[];
  provenance: { kind: string; blocks?: number; cache_hits?: number };
  events_sha256: string;
};
type FrameProof = {
  dataset: string;
  window: string;
  requested_ms: number;
  actual_ms: number;
  error_ms: number;
  session_s: number;
  events_sha256: string;
  reconstructed: true;
  external_assets: "blocked";
};
const element = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const select = element<HTMLSelectElement>("dataset");
const tabs = element<HTMLSelectElement>("window");
const position = element<HTMLInputElement>("seconds");
const slider = element<HTMLInputElement>("timeline");
const status = element("status");
const content = element("content");
const stage = element("stage");
const fps = element<HTMLInputElement>("fps");
let manifest: Manifest;
let windows: Record<string, eventWithTime[]>;
let replayer: Replayer | null = null;
let active: Tab | null = null;
let playing: ReturnType<typeof setInterval> | null = null;
let busy = false;
let generation = 0;
const globalLab = window as typeof window & {
  lab: {
    ready: boolean;
    errors: string[];
    load: typeof load;
    seek: typeof seek;
    state: () => FrameProof | null;
    exportMode: () => void;
  };
};
let proof: FrameProof | null = null;
const errors: string[] = [];

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error("Arquivo local indisponível.");
  return response.json();
}
function fail(error: unknown) {
  stop();
  const message = error instanceof Error ? error.message : "Falha no player local.";
  errors.push(message);
  status.textContent = message;
}
function stop() {
  if (playing) clearInterval(playing);
  playing = null;
  element("play").textContent = "Reproduzir";
}
function fit() {
  if (!replayer) return;
  const width = Number.parseFloat(replayer.iframe.width);
  const height = Number.parseFloat(replayer.iframe.height);
  if (!width || !height) return;
  const scale = Math.min(stage.clientWidth / width, stage.clientHeight / height);
  content.style.width = `${width}px`;
  content.style.height = `${height}px`;
  content.style.transform = `translate(${(stage.clientWidth - width * scale) / 2}px, ${(stage.clientHeight - height * scale) / 2}px) scale(${scale})`;
}
function mount(tab: Tab) {
  replayer?.destroy();
  content.replaceChildren();
  active = tab;
  tabs.value = tab.id;
  replayer = new Replayer(windows[tab.id], {
    ...COMMON_REPLAYER_CONFIG,
    root: content,
    skipInactive: false,
    showWarning: false,
    showDebug: false,
    mouseTail: false,
    loadTimeout: 0,
    insertStyleRules: [...COMMON_REPLAYER_CONFIG.insertStyleRules!, ...speedDependentStyleRules(2)],
  });
  replayer.on("resize", fit);
  fit();
}

async function seek(seconds: number, windowId?: string): Promise<FrameProof> {
  if (busy) throw new Error("Aguarde a reconstrução em andamento.");
  if (!manifest || !Number.isFinite(seconds) || seconds < 0 || seconds > manifest.duration_s)
    throw new Error("Instante fora da sessão.");
  busy = true;
  proof = null;
  const target = manifest.start + Math.round(seconds * 1000);
  const tab = chooseWindow(manifest.windows, target, windowId);
  try {
    if (!tab) {
      content.style.visibility = "hidden";
      throw new Error("Sem imagem gravada neste intervalo/aba.");
    }
    content.style.visibility = "visible";
    if (active?.id !== tab.id || !replayer) mount(tab);
    const snapshot = windows[tab.id].some((e) => e.type === 2 && e.timestamp <= target);
    if (!snapshot) throw new Error("Ainda não há snapshot completo nessa aba.");
    const player = replayer!;
    player.pause(target - tab.start);
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
    // CSS capturado pode revelar elementos com animação; duração reduzida upstream precisa assentar.
    await new Promise((resolve) => setTimeout(resolve, 40));
    fit();
    const actual = tab.start + player.getCurrentTime();
    const error = Math.abs(actual - target);
    if (error > 5) throw new Error("Reconstrução não atingiu o instante solicitado.");
    proof = {
      dataset: manifest.name,
      window: tab.id,
      requested_ms: target,
      actual_ms: actual,
      error_ms: error,
      session_s: seconds,
      events_sha256: manifest.events_sha256,
      reconstructed: true,
      external_assets: "blocked",
    };
    position.value = seconds.toFixed(3);
    slider.value = String(seconds);
    status.textContent = `${seconds.toFixed(3)}s · aba ${tab.id} · desvio ${error.toFixed(1)}ms · DOM reconstruído`;
    return proof;
  } finally {
    busy = false;
  }
}

async function load(name: string) {
  if (!/^[a-z0-9][a-z0-9-]{0,60}$/.test(name)) throw new Error("Sessão local inválida.");
  const current = ++generation;
  globalLab.lab.ready = false;
  stop();
  status.textContent = "Preparando sessão local…";
  const [data, events] = await Promise.all([
    get<Manifest>(`/datasets/${name}/manifest.json`),
    get<Record<string, eventWithTime[]>>(`/datasets/${name}/events.json`),
  ]);
  if (current !== generation) return;
  manifest = data;
  windows = events;
  select.value = name;
  tabs.replaceChildren(...manifest.windows.map((w) => new Option(`Aba ${w.id}`, w.id)));
  replayer?.destroy();
  replayer = null;
  active = null;
  slider.max = String(manifest.duration_s);
  position.max = String(manifest.duration_s);
  const clicks = manifest.windows.reduce((n, w) => n + w.clicks, 0);
  element("summary").textContent =
    `${manifest.windows.length} aba(s) · ${manifest.duration_s.toFixed(1)}s · ${clicks} cliques. Origem: ${manifest.provenance.kind === "api_snapshots" ? `API · ${manifest.provenance.blocks} blocos · ${manifest.provenance.cache_hits} em cache` : "arquivo local"}.`;
  element<HTMLAnchorElement>("report").href = `/datasets/${name}/insights.md`;
  element("evidence").replaceChildren(
    ...manifest.evidence.map((item) => {
      const button = document.createElement("button");
      const time = document.createElement("time");
      time.textContent = `${item.session_s.toFixed(3)}s · aba ${item.window}`;
      button.append(
        time,
        document.createTextNode(`${item.kind} · ${item.control || item.path || item.state || ""}`),
      );
      button.onclick = () => {
        stop();
        void seek(item.session_s, item.window).catch(fail);
      };
      return button;
    }),
  );
  const first = manifest.windows[0];
  const anchor = windows[first.id].find((e) => e.type === 2)!;
  await seek((anchor.timestamp - manifest.start) / 1000, first.id);
  globalLab.lab.ready = true;
}

globalLab.lab = {
  ready: false,
  errors,
  load,
  seek,
  state: () => proof,
  exportMode: () => {
    stop();
    document.body.classList.add("export");
    fit();
  },
};
select.onchange = () => {
  void load(select.value).catch(fail);
};
tabs.onchange = () => {
  stop();
  const tab = manifest.windows.find((w) => w.id === tabs.value)!;
  const anchor = windows[tab.id].find((e) => e.type === 2)!;
  void seek((anchor.timestamp - manifest.start) / 1000, tab.id).catch(fail);
};
element("seek").onclick = () => {
  stop();
  void seek(Number(position.value), tabs.value).catch(fail);
};
slider.onchange = () => {
  stop();
  void seek(Number(slider.value), tabs.value).catch(fail);
};
for (const [id, direction] of [
  ["back", -1],
  ["next", 1],
] as const) {
  element(id).onclick = () => {
    stop();
    const rate = Number(fps.value);
    if (!Number.isFinite(rate) || rate < 1 || rate > 30)
      return fail(new Error("FPS deve estar entre 1 e 30."));
    void seek(
      Math.max(0, Math.min(manifest.duration_s, Number(position.value) + direction / rate)),
      tabs.value,
    ).catch(fail);
  };
}
element("play").onclick = () => {
  if (playing) return stop();
  element("play").textContent = "Pausar";
  playing = setInterval(() => {
    if (busy) return;
    const next = Number(position.value) + 1 / 6;
    if (next > manifest.duration_s) return stop();
    void seek(next, tabs.value).catch(fail);
  }, 1000 / 6);
};
addEventListener("resize", fit);
void get<{ name: string }[]>("/catalog.json")
  .then((catalog) => {
    select.replaceChildren(...catalog.map((item) => new Option(item.name, item.name)));
    if (!catalog.length) throw new Error("Prepare uma sessão antes de abrir o laboratório.");
    const requested = new URLSearchParams(location.search).get("dataset");
    return load(requested || catalog[0].name);
  })
  .catch(fail);
