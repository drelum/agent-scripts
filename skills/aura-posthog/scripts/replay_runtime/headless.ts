// Adaptador local: controlador de abas e escala originais do PostHog.
import { Replayer } from "posthog-js/rrweb";
import type { eventWithTime } from "posthog-js/rrweb-types";
import {
  COMMON_REPLAYER_CONFIG,
  speedDependentStyleRules,
  getHrefFromSnapshot,
} from "@posthog/replay-shared";
import type { RecordingSegment } from "@posthog/replay-shared";
import { PlaybackController } from "./vendor/posthog/replay-headless/src/playback-controller";
import { ViewportScaler } from "./vendor/posthog/replay-headless/src/viewport-scaler";
import { HostBridge } from "./vendor/posthog/replay-headless/src/host-bridge";

type Source = {
  start: number;
  segments: RecordingSegment[];
  windows: Record<string, eventWithTime[]>;
  window?: string;
};
type CaptureState = { session_ms: number; window: string; stopped: boolean; url: string };
const scope = window as typeof window & {
  captureSource: Source;
  captureLab: {
    ready: boolean;
    start: (seconds: number) => void;
    state: () => CaptureState | null;
  };
};
const source = scope.captureSource;
const root = document.getElementById("content")!;
const windows = Object.entries(source.windows)
  .filter(([id]) => !source.window || id === source.window)
  .map(([id, events]) => {
    const container = document.createElement("div");
    Object.assign(container.style, { position: "absolute", inset: "0", visibility: "hidden" });
    root.append(container);
    const replayer = new Replayer(events, {
      ...COMMON_REPLAYER_CONFIG,
      root: container,
      skipInactive: false,
      useVirtualDom: false,
      loadTimeout: 0,
      mouseTail: false,
      showWarning: false,
      showDebug: false,
      insertStyleRules: [
        ...COMMON_REPLAYER_CONFIG.insertStyleRules!,
        ...speedDependentStyleRules(2),
      ],
    });
    return {
      windowId: Number(id),
      replayer,
      root: container,
      firstTimestamp: events[0].timestamp,
      lastTimestamp: events.at(-1)!.timestamp,
      hrefChanges: events.flatMap((event) => {
        const href = getHrefFromSnapshot(event);
        return typeof href === "string" ? [{ timestamp: event.timestamp, href }] : [];
      }),
    };
  });
if (!windows.length) throw new Error("Aba sem eventos.");
const segments = source.window
  ? [
      {
        kind: "window" as const,
        windowId: windows[0].windowId,
        startTimestamp: windows[0].firstTimestamp,
        endTimestamp: windows[0].lastTimestamp,
        durationMs: windows[0].lastTimestamp - windows[0].firstTimestamp,
        isActive: true,
      },
    ]
  : source.segments;
const controller = new PlaybackController(
  windows,
  segments,
  source.start,
  { skipInactivity: false },
  new HostBridge(),
);
const scaler = new ViewportScaler(root, 0);
for (const tab of windows)
  scaler.attachToReplayer(tab.replayer, () => controller.activeWindow === tab);
controller.onWindowChange((visible) => {
  for (const tab of windows) tab.root.style.visibility = tab === visible ? "visible" : "hidden";
  scaler.fitReplayer(visible.replayer);
});
let started = false;
scope.captureLab = {
  ready: true,
  start(seconds) {
    controller.start(seconds * 1000);
    started = true;
  },
  state() {
    if (!started) return null;
    const sessionMs = source.start + controller.currentSessionMs();
    const tab = windows.find(
      (candidate) => candidate.windowId === controller.activeWindow.windowId,
    )!;
    // Histórico da aba exibida: seeks rrweb podem não emitir os Custom events de URL.
    let low = 0;
    let high = tab.hrefChanges.length;
    while (low < high) {
      const mid = (low + high) >>> 1;
      if (tab.hrefChanges[mid].timestamp <= sessionMs) low = mid + 1;
      else high = mid;
    }
    return {
      session_ms: sessionMs,
      window: String(controller.activeWindow.windowId),
      url: low ? tab.hrefChanges[low - 1].href : "",
      stopped: controller.isStopped,
    };
  },
};
