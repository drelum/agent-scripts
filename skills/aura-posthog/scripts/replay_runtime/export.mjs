// Pipeline único: captura virtual contínua e índice observado em cada beginFrame.
import { capture } from "puppeteer-capture";
import { launchCaptureBrowser } from "./browser.mjs";
import { resolve, join } from "node:path";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { cutWindow, validateFrames } from "./capture-proof.mjs";
import { captureJobs } from "./capture-batch.mjs";
const root = import.meta.dirname;
const began = performance.now();
const args = process.argv.slice(2);
function arg(name, fallback) {
  const i = args.indexOf(name);
  if (i < 0) return fallback;
  if (!args[i + 1] || args[i + 1].startsWith("--")) throw new Error(`Valor ausente: ${name}`);
  return args[i + 1];
}
const dataset = arg("--dataset");
if (!dataset || !/^[a-z0-9][a-z0-9-]{0,60}$/.test(dataset)) throw new Error("Dataset inválido.");
const batchFile = arg("--batch");
const jobs = batchFile
  ? JSON.parse(readFileSync(batchFile, "utf8"))
  : [
      {
        start: Number(arg("--start", "0")),
        duration: Number(arg("--duration", "10")),
        fps: Number(arg("--fps", "12")),
        window: arg("--window"),
        output: arg("--output"),
      },
    ];
if (!Array.isArray(jobs) || !jobs.length || jobs.length > 1000)
  throw new Error("Lote exige 1–1000 recortes.");
const outputs = new Set();
for (const job of jobs) {
  if (
    !job.output ||
    !Number.isFinite(job.start) ||
    job.start < 0 ||
    !Number.isFinite(job.duration) ||
    job.duration <= 0 ||
    job.duration > 600 ||
    !Number.isInteger(job.fps) ||
    job.fps < 1 ||
    job.fps > 30
  )
    throw new Error("Recorte, FPS (1–30) e saída nova obrigatórios.");
  const output = resolve(job.output);
  if (outputs.has(output) || existsSync(output)) throw new Error("Saída deve ser nova e única.");
  outputs.add(output);
}
process.umask(0o077);
const folder = join(root, "private/datasets", dataset);
const catalog = JSON.parse(readFileSync(join(root, "private/catalog.json"), "utf8"));
if (!catalog.some((item) => item.name === dataset)) throw new Error("Dataset invalidado.");
const manifest = JSON.parse(readFileSync(join(folder, "manifest.json"), "utf8"));
const eventBytes = readFileSync(join(folder, "events.json"));
const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
if (sha(eventBytes) !== manifest.events_sha256)
  throw new Error("Integridade dos eventos inválida.");
const windows = JSON.parse(eventBytes);
const executable = process.env.PUPPETEER_EXECUTABLE_PATH;
if (!executable || !existsSync(executable))
  throw new Error("Defina PUPPETEER_EXECUTABLE_PATH para chrome-headless-shell Linux.");
const rendererHash = sha(
  Buffer.concat([
    readFileSync(join(root, "export.mjs")),
    readFileSync(join(root, "browser.mjs")),
    readFileSync(join(root, "capture-batch.mjs")),
    readFileSync(join(root, "private/headless.js")),
    readFileSync(join(root, "capture-proof.mjs")),
    readFileSync(join(root, "recording_coverage.py")),
    readFileSync(join(root, "package-lock.json")),
  ]),
);
const datasetMs = performance.now() - began;
async function renderChunk(browser, { start, duration, fps, window: windowId, output: outputArg }) {
  const chunkBegan = performance.now();
  const timings = { begin_frame_ms: 0, state_read_ms: 0, captured_ticks: 0 };
  let phase = chunkBegan;
  function measure(name) {
    const now = performance.now();
    timings[name] = now - phase;
    phase = now;
  }
  const target = manifest.start + start * 1000;
  const selected = windowId ? manifest.windows.find((tab) => tab.id === windowId) : null;
  if (windowId && (!selected || target < selected.start || target + duration * 1000 > selected.end))
    throw new Error("Recorte fora da aba.");
  if (start + duration > manifest.duration_s) throw new Error("Recorte fora da sessão.");
  const initialTabs = selected
    ? [selected]
    : manifest.windows.filter((tab) => tab.start <= target && tab.end >= target);
  if (
    !initialTabs.some((tab) =>
      windows[tab.id].some((event) => event.type === 2 && event.timestamp <= target),
    )
  )
    throw new Error("Início sem snapshot completo.");
  // Enviar ao browser só a cadeia necessária: Meta + snapshot completo + mutações até o recorte.
  const warmTarget = manifest.start + Math.max(0, start - 2) * 1000;
  const captureEnd = target + duration * 1000;
  const boundedWindows = {};
  for (const tab of manifest.windows) {
    if ((windowId && tab.id !== windowId) || tab.end < warmTarget || tab.start > captureEnd)
      continue;
    boundedWindows[tab.id] = cutWindow(
      windows[tab.id],
      Math.max(warmTarget, tab.start),
      captureEnd,
    );
  }
  const output = resolve(outputArg);
  process.umask(0o077);
  mkdirSync(output, { mode: 0o700 });
  measure("preflight_ms");
  const frames = [];
  const count = Math.ceil(duration * fps);
  let recorder;
  let latest = null;
  let finish;
  let fail;
  const done = new Promise((yes, no) => {
    finish = yes;
    fail = no;
  });
  // Evitar rejeição sem consumidor durante a inicialização do encoder.
  done.catch(() => {});
  let timer;
  let closing = false;
  let captureComplete = false;
  let result;
  let page;
  try {
    page = await browser.newPage();
    await page.setViewport({ width: 1366, height: 768 });
    await page.setRequestInterception(true);
    const playerURL = "http://replay-capture.localhost/";
    const script = readFileSync(join(root, "private/headless.js"), "utf8");
    const html = `<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#f1eee6;overflow:hidden}#content{position:absolute}.replayer-wrapper{position:relative}.replayer-mouse{position:absolute;width:10px;height:10px;border:2px solid white;border-radius:50%;background:#dc432e}</style><div id="content"></div><script>${script.replaceAll("</script", "<\\/script")}</script>`;
    page.on("request", (request) => {
      if (request.url() === playerURL)
        void request.respond({ status: 200, contentType: "text/html", body: html });
      else if (/^(data:|blob:|about:blank$)/.test(request.url())) void request.continue();
      else void request.abort();
    });
    page.on("pageerror", () => {
      if (!closing) fail(new Error("Exceção no replayer; artefato não publicado."));
    });
    page.on("error", () => fail(new Error("Página de captura interrompida.")));
    await page.evaluateOnNewDocument(
      (source) => {
        window.captureSource = source;
      },
      {
        start: manifest.start,
        segments: manifest.segments,
        windows: boundedWindows,
        window: windowId,
      },
    );
    await page.goto(playerURL, { waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => window.captureLab?.ready, { timeout: 20000 });
    measure("player_setup_ms");
    // O índice é lido depois da pintura, antes de liberar o próximo tick virtual.
    const createSession = page.createCDPSession.bind(page);
    page.createCDPSession = async () => {
      const session = await createSession();
      const send = session.send.bind(session);
      session.send = async (method, params, ...rest) => {
        if (method === "HeadlessExperimental.beginFrame")
          params = { ...params, screenshot: { format: "jpeg", quality: 85 } };
        const tick = performance.now();
        const result = await send(method, params, ...rest);
        if (method === "HeadlessExperimental.beginFrame") {
          timings.begin_frame_ms += performance.now() - tick;
          timings.captured_ticks++;
        }
        if (method === "HeadlessExperimental.beginFrame" && result.screenshotData) {
          const read = performance.now();
          latest = await page.evaluate(() => window.captureLab.state());
          timings.state_read_ms += performance.now() - read;
        }
        return result;
      };
      return session;
    };
    recorder = await capture(page, {
      fps,
      ffmpeg: "ffmpeg",
      format: async () => {},
      customFfmpegConfig: async (ffmpeg) => {
        ffmpeg.outputOptions(["-c:v libx264", "-pix_fmt yuv420p", "-crf 18"]);
        ffmpeg.on("error", () => fail(new Error("Encoder interrompido; vídeo não publicado.")));
      },
    });
    recorder.dropCapturedFrames = true;
    recorder.on("frameCaptureFailed", () => fail(new Error("Captura interrompida.")));
    recorder.on("captureStopped", () => {
      if (!captureComplete && !closing) fail(new Error("Captura terminou antes do recorte."));
    });
    recorder.on("frameCaptured", () => {
      recorder.dropCapturedFrames =
        !latest ||
        latest.session_ms < target ||
        latest.session_ms >= captureEnd ||
        frames.length >= count;
      const previous = frames.at(-1);
      if (previous && latest?.session_ms <= previous.session_ms) {
        recorder.dropCapturedFrames = true;
        if (latest.session_ms < previous.session_ms)
          fail(
            new Error(
              `Relógio regressivo na troca de aba: ${previous.window}/${previous.session_s} → ${latest.window}/${(latest.session_ms - manifest.start) / 1000}.`,
            ),
          );
      }
      if (latest?.session_ms >= captureEnd && frames.length) finish();
      else if (latest?.stopped && frames.length < count)
        fail(new Error("Reprodução terminou antes de completar o recorte."));
    });
    recorder.on("frameRecorded", (index, virtualMs, bytes) => {
      frames.push({
        index,
        video_s: index / fps,
        session_ms: latest.session_ms,
        session_s: (latest.session_ms - manifest.start) / 1000,
        window: latest.window,
        url: latest.url,
        capture_virtual_ms: virtualMs,
        capture_sha256: sha(bytes),
      });
      if (frames.length === count) finish();
    });
    timer = setTimeout(() => fail(new Error("Tempo máximo de captura excedido.")), 180000);
    await Promise.race([
      recorder.start(join(output, "clip.mp4"), { dropCapturedFrames: true }),
      done,
    ]);
    const warm = Math.max(
      start - 2,
      (Math.min(
        ...initialTabs.map((tab) => windows[tab.id].find((event) => event.type === 2).timestamp),
      ) -
        manifest.start) /
        1000,
    );
    await page.evaluate((seconds) => window.captureLab.start(seconds), warm);
    measure("capture_setup_ms");
    await done;
    captureComplete = true;
    measure("capture_ms");
    await recorder.stop();
    measure("encoder_stop_ms");
    clearTimeout(timer);
    const probe = JSON.parse(
      execFileSync(
        "ffprobe",
        ["-v", "error", "-count_frames", "-show_streams", "-of", "json", join(output, "clip.mp4")],
        { encoding: "utf8" },
      ),
    );
    const video = probe.streams.find((stream) => stream.codec_type === "video");
    validateFrames(frames, Number(video.nb_read_frames), fps, target, windowId);
    measure("frame_validation_ms");
    execFileSync(
      "ffmpeg",
      ["-v", "error", "-nostdin", "-i", join(output, "clip.mp4"), "-f", "null", "-"],
      { stdio: ["ignore", "ignore", "pipe"] },
    );
    measure("decode_validation_ms");
    result = {
      schema: 1,
      status: "complete",
      dataset,
      fps,
      selected_window: windowId || null,
      renderer_sha256: rendererHash,
      start_s: start,
      requested_duration_s: duration,
      encoded_duration_s: frames.length / fps,
      timeline_gaps: frames.flatMap((frame, i) =>
        i && frame.session_ms - frames[i - 1].session_ms > 1000 / fps + 5
          ? [
              {
                after_frame: i - 1,
                before_frame: i,
                from_ms: frames[i - 1].session_ms,
                to_ms: frame.session_ms,
              },
            ]
          : [],
      ),
      browser_events: Object.values(boundedWindows).reduce(
        (total, events) => total + events.length,
        0,
      ),
      frames,
      events_sha256: manifest.events_sha256,
      video_sha256: sha(readFileSync(join(output, "clip.mp4"))),
      total_ms: performance.now() - chunkBegan,
      width: video.width,
      height: video.height,
      limitations: [
        "DOM reconstruído; assets externos bloqueados.",
        "Animações reduzidas; fidelidade visual absoluta não demonstrada.",
        "Índice mede o relógio rrweb na captura; não sincroniza relógio do backend.",
      ],
    };
  } finally {
    closing = true;
    clearTimeout(timer);
    const close = performance.now();
    try {
      if (recorder?.isCapturing) await recorder.stop();
      if (recorder) await recorder.detach();
    } finally {
      if (page) await page.close();
      timings.page_close_ms = performance.now() - close;
    }
  }
  result.total_ms = performance.now() - chunkBegan;
  result.timings = timings;
  writeFileSync(join(output, "export.json"), JSON.stringify(result, null, 2), { mode: 0o600 });
  return {
    frames: frames.length,
    total_ms: result.total_ms,
    duration_s: result.encoded_duration_s,
    timings,
    output,
  };
}
const browserTimings = [];
const results = await captureJobs(jobs, {
  workers: Number(arg("--workers", "2")),
  open: async () => {
    const start = performance.now();
    const browser = await launchCaptureBrowser(executable);
    browserTimings.push({ launch_ms: performance.now() - start, browser });
    return browser;
  },
  run: renderChunk,
  close: async (browser) => {
    const start = performance.now();
    await browser.close();
    browserTimings.find((entry) => entry.browser === browser).close_ms = performance.now() - start;
  },
});
console.log(
  JSON.stringify({
    dataset_ms: datasetMs,
    total_ms: performance.now() - began,
    browsers: browserTimings.map(({ launch_ms, close_ms }) => ({ launch_ms, close_ms })),
    chunks: results,
  }),
);
