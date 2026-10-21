// Mesmo contrato do BrowserPool PostHog: validar o processo iniciado, não --version.
import { launch } from "puppeteer-capture";
import { basename } from "node:path";
import { pathToFileURL } from "node:url";

export async function launchCaptureBrowser(executable = process.env.PUPPETEER_EXECUTABLE_PATH) {
  if (!executable) throw new Error("PUPPETEER_EXECUTABLE_PATH ausente.");
  const browser = await launch({
    executablePath: executable,
    args: ["--disable-dev-shm-usage", "--mute-audio"],
    env: Object.fromEntries(
      ["PATH", "HOME", "LANG", "TZ"]
        .filter((key) => process.env[key] !== undefined)
        .map((key) => [key, process.env[key]]),
    ),
  });
  if (basename(browser.process()?.spawnfile ?? "") !== "chrome-headless-shell") {
    await browser.close();
    throw new Error("Captura exige chrome-headless-shell; processo iniciado incompatível.");
  }
  return browser;
}

async function preflight() {
  const browser = await launchCaptureBrowser();
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 320, height: 240 });
    await page.setContent("<body style='background:#246'>Teste local de captura</body>");
    const session = await page.createCDPSession();
    await session.send("HeadlessExperimental.enable");
    let frame;
    // O primeiro tick pode apenas preparar o compositor, sem screenshot.
    for (let tick = 0; tick < 3; tick++) {
      frame = await session.send("HeadlessExperimental.beginFrame", {
        frameTimeTicks: (tick * 1000) / 3,
        interval: 1000 / 3,
        noDisplayUpdates: false,
        screenshot: { format: "jpeg", quality: 50 },
      });
      if (frame.screenshotData) break;
    }
    if (!frame.screenshotData) throw new Error("Pré-teste sem frame capturado.");
    await page.close();
    return { ready: true, protocol: "HeadlessExperimental.beginFrame" };
  } finally {
    await browser.close();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    console.log(JSON.stringify(await preflight()));
  } catch {
    // Não imprimir argumentos, ambiente ou stderr do Chrome.
    console.log(
      JSON.stringify({ ready: false, reason: "chrome-headless-shell ou captura incompatível" }),
    );
    process.exitCode = 1;
  }
}
