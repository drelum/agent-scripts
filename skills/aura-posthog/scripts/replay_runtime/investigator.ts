import { frameSeekTime } from "./video-time";

type Frame = {
  index: number;
  video_s: number;
  session_s: number;
  session_ms: number;
  window: string;
};
type Evidence = {
  id: string;
  kind: string;
  summary: string;
  session_s?: number;
  window?: string;
  frame_index: number | null;
};
type Bundle = {
  name: string;
  fps: number;
  frames: Frame[];
  events: Evidence[];
  limits: string[];
  findings: { observation: string; hypothesis: string; frames: number[]; events: string[] }[];
};
type Relation = { method: string; approximate: boolean; event: Evidence };
const node = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const video = node<HTMLVideoElement>("video");
const catalog = node<HTMLSelectElement>("bundles");
const query = node<HTMLInputElement>("search");
const clock = node<HTMLInputElement>("session-time");
let bundle: Bundle;
let index = 0;
let loading = 0;
let actionBusy = false;
function actions(disabled: boolean) {
  catalog.disabled = disabled;
  for (const id of ["snapshot", "ticket", "go", "back", "next"])
    node<HTMLButtonElement>(id).disabled = disabled;
}
const message = (text: string) => {
  node("notice").textContent = text;
};
async function api<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(
    path,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {},
  );
  if (!response.ok) throw new Error("Operação local recusada. Confira o pacote e o instante.");
  return response.json();
}
function error(reason: unknown) {
  message(reason instanceof Error ? reason.message : "Falha na investigação.");
}
function reference(frame: Frame) {
  return `${frame.session_s.toFixed(3)}s · aba ${frame.window} · frame ${frame.index}`;
}
function update() {
  if (!bundle) return;
  index = Math.min(
    bundle.frames.length - 1,
    Math.max(0, Math.floor(video.currentTime * bundle.fps + 0.001)),
  );
  const frame = bundle.frames[index];
  clock.value = frame.session_s.toFixed(3);
  node("clock").textContent = reference(frame);
  const url = new URL(location.href);
  url.search = new URLSearchParams({ bundle: bundle.name, frame: String(index) }).toString();
  history.replaceState(null, "", url);
}
async function seek(frameIndex: number) {
  if (!Number.isInteger(frameIndex) || frameIndex < 0 || frameIndex >= bundle.frames.length)
    throw new Error("Frame fora do vídeo.");
  video.pause();
  index = frameIndex;
  const target = frameSeekTime(index, bundle.fps);
  if (Math.abs(video.currentTime - target) > 0.00001) {
    const finished = new Promise<void>((resolve) =>
      video.addEventListener("seeked", () => resolve(), { once: true }),
    );
    video.currentTime = target;
    await finished;
  }
  update();
}
async function context(event: Evidence) {
  const generation = loading;
  const data = await api<{ event: Evidence; related: Relation[] }>(
    `/api/bundles/${bundle.name}/context?event=${encodeURIComponent(event.id)}`,
  );
  if (generation !== loading) return;
  node("context").replaceChildren();
  const paragraph = document.createElement("p");
  paragraph.textContent = `${data.event.id} · ${data.event.kind} · ${data.event.summary}`;
  node("context").append(paragraph);
  if (!data.related.length)
    node("context").append(document.createTextNode("Sem evidência relacionada disponível."));
  for (const item of data.related) {
    const p = document.createElement("p");
    p.textContent = `${item.approximate ? "Associação aproximada" : "Identificador compartilhado"} (${item.method}) · ${item.event.kind} · ${item.event.summary}`;
    node("context").append(p);
  }
  if (event.frame_index !== null) await seek(event.frame_index);
  else message("Evento sem imagem neste recorte/aba. Contexto disponível abaixo.");
}
function list() {
  const term = query.value.toLocaleLowerCase("pt-BR");
  const events = bundle.events.filter((event) =>
    `${event.kind} ${event.summary}`.toLocaleLowerCase("pt-BR").includes(term),
  );
  node("matches").textContent = `${events.length} eventos encontrados`;
  node("events").replaceChildren(
    ...events.map((event) => {
      const button = document.createElement("button");
      button.className = "event";
      button.textContent = `${event.session_s?.toFixed(3) ?? "backend"}s · ${event.kind} · ${event.summary}${event.frame_index === null ? " · sem imagem" : ""}`;
      button.onclick = () => {
        void context(event).catch(error);
      };
      return button;
    }),
  );
}
async function load(name: string, requested = 0) {
  const generation = ++loading;
  actions(true);
  video.pause();
  const data = await api<Bundle>(`/api/bundles/${name}`);
  if (generation !== loading) return;
  bundle = data;
  query.value = "";
  node("context").replaceChildren();
  node("attachments").replaceChildren();
  node("ticket-text").textContent = "";
  catalog.value = name;
  const ready = new Promise<void>((resolve, reject) => {
    video.onloadedmetadata = () => resolve();
    video.onerror = () => reject(new Error("Vídeo local indisponível."));
  });
  video.src = `/bundles/${name}/clip.mp4`;
  await ready;
  if (generation !== loading) return;
  node("limits").textContent = bundle.limits.join(" ");
  node("findings").replaceChildren(
    ...(bundle.findings || []).map((finding) => {
      const button = document.createElement("button");
      button.className = "event";
      button.textContent = `${finding.observation}${finding.hypothesis ? ` · hipótese: ${finding.hypothesis}` : ""}`;
      button.onclick = () => {
        void seek(finding.frames[0]).catch(error);
      };
      return button;
    }),
  );
  list();
  await seek(requested);
  actions(actionBusy);
  message("Sessão pronta. Busque um evento ou escolha um instante.");
}
video.ontimeupdate = update;
video.onseeked = update;
query.oninput = list;
catalog.onchange = () => {
  void load(catalog.value).catch(error);
};
node("go").onclick = () => {
  const target = Number(clock.value);
  const nearest = bundle.frames.reduce((best, frame) =>
    Math.abs(frame.session_s - target) < Math.abs(best.session_s - target) ? frame : best,
  );
  if (
    clock.value.trim() === "" ||
    !Number.isFinite(target) ||
    Math.abs(nearest.session_s - target) > 1 / bundle.fps + 0.005
  )
    return message("Sem imagem nesse instante. Confira a cobertura do recorte.");
  void seek(nearest.index).catch(error);
};
for (const [id, delta] of [
  ["back", -1],
  ["next", 1],
] as const)
  node(id).onclick = () => {
    void seek(index + delta).catch(error);
  };
node("snapshot").onclick = async () => {
  if (actionBusy) return;
  const name = bundle.name,
    generation = loading;
  actionBusy = true;
  actions(true);
  try {
    video.pause();
    update();
    const shot = await api<Frame & { file: string }>(`/api/bundles/${name}/snapshot`, {
      index,
    });
    if (generation !== loading) return;
    const link = document.createElement("a");
    link.href = `/bundles/${name}/snapshots/${shot.file}`;
    link.download = shot.file;
    link.textContent = `Baixar snapshot · ${reference(shot)}`;
    node("attachments").append(link);
    message("Snapshot extraído do vídeo, com referência temporal.");
  } catch (reason) {
    error(reason);
  } finally {
    actionBusy = false;
    if (generation === loading) actions(false);
  }
};
node("ticket").onclick = async () => {
  if (actionBusy) return;
  const name = bundle.name,
    generation = loading;
  actionBusy = true;
  actions(true);
  try {
    video.pause();
    update();
    const result = await api<{ id: string; markdown: string }>(`/api/bundles/${name}/ticket`, {
      index,
      title: node<HTMLInputElement>("title").value,
    });
    if (generation !== loading) return;
    node("ticket-text").textContent = result.markdown;
    const link = document.createElement("a");
    link.href = `/bundles/${name}/tickets/${result.id}/ticket.zip`;
    link.download = "ticket.zip";
    link.textContent = "Baixar ticket + sequência de snapshots + referências";
    node("attachments").append(link);
    message("Pacote de evidências pronto para anexar ao ticket.");
  } catch (reason) {
    error(reason);
  } finally {
    actionBusy = false;
    if (generation === loading) actions(false);
  }
};
void api<{ name: string }[]>("/api/bundles")
  .then(async (items) => {
    catalog.replaceChildren(...items.map((item) => new Option(item.name, item.name)));
    if (!items.length) throw new Error("Prepare um pacote pelo comando investigate.py build.");
    const params = new URLSearchParams(location.search);
    await load(params.get("bundle") || items[0].name, Number(params.get("frame") || 0));
  })
  .catch(error);
