// A evidência só é publicada quando o encoder e o índice concordam.
export function cutWindow(events, fromMs, untilMs) {
  let snapshotIndex = -1;
  for (let i = 0; i < events.length; i++) {
    if (events[i].type === 2 && events[i].timestamp <= fromMs) snapshotIndex = i;
  }
  if (snapshotIndex < 0) snapshotIndex = events.findIndex((event) => event.type === 2);
  if (snapshotIndex < 0) throw new Error("Aba sem snapshot completo.");
  let first = snapshotIndex;
  for (let i = snapshotIndex - 1; i >= 0; i--) {
    if (events[i].type === 4) {
      first = i;
      break;
    }
  }
  const after = events.findIndex((event) => event.timestamp > untilMs);
  return events.slice(first, after < 0 ? events.length : after + 1);
}

export function validateFrames(frames, encodedCount, fps, targetMs, windowId) {
  if (!frames.length || encodedCount !== frames.length)
    throw new Error("Contagem de frames divergente.");
  if (frames[0].session_ms < targetMs || frames[0].session_ms - targetMs > 1000 / fps + 5)
    throw new Error("Início do vídeo deslocado.");
  for (let i = 0; i < frames.length; i++) {
    const frame = frames[i];
    if (
      frame.index !== i ||
      frame.video_s !== i / fps ||
      !Number.isFinite(frame.session_ms) ||
      !frame.window ||
      (windowId && frame.window !== windowId)
    )
      throw new Error("Índice de frame inválido.");
    if (i && frame.session_ms <= frames[i - 1].session_ms)
      throw new Error("Relógio parado ou regressivo.");
    if (
      i &&
      frame.window === frames[i - 1].window &&
      Math.abs(frame.session_ms - frames[i - 1].session_ms - 1000 / fps) > 5
    )
      throw new Error("Cadência do rrweb divergente.");
  }
}
