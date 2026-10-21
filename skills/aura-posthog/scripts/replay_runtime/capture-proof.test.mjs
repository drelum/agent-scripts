import { test } from "node:test";
import assert from "node:assert/strict";
import { cutWindow, validateFrames } from "./capture-proof.mjs";
const frames = () =>
  Array.from({ length: 3 }, (_, index) => ({
    index,
    video_s: index / 10,
    session_ms: 1000 + index * 100,
    window: "2",
  }));
void test("recorte preserva Meta, último snapshot completo e todas as mutações intermediárias", () => {
  const events = [
    { type: 4, timestamp: 0 },
    { type: 2, timestamp: 1 },
    { type: 3, timestamp: 2 },
    { type: 4, timestamp: 3 },
    { type: 2, timestamp: 4 },
    { type: 3, timestamp: 5 },
    { type: 3, timestamp: 6 },
    { type: 3, timestamp: 7 },
    { type: 2, timestamp: 8 },
  ];
  assert.deepEqual(cutWindow(events, 5, 6), events.slice(3, 8));
  assert.throws(() => cutWindow([{ type: 3, timestamp: 0 }], 0, 1));
});
void test("captura indexada aceita somente encoder e relógio concordantes", () => {
  assert.doesNotThrow(() => validateFrames(frames(), 3, 10, 1000, "2"));
  assert.throws(() => validateFrames(frames(), 2, 10, 1000, "2"));
  assert.throws(() => validateFrames(frames(), 3, 10, 1000, "1"));
  assert.throws(() => validateFrames(frames(), 3, 10, 500, "2"));
});
void test("não publicar duplicação, regressão ou salto dentro da mesma aba", () => {
  for (const timestamp of [1000, 999, 1500]) {
    const corrupted = frames();
    corrupted[1].session_ms = timestamp;
    assert.throws(() => validateFrames(corrupted, 3, 10, 1000, "2"));
  }
});
void test("salto entre abas mantém referência observada sem inventar frames da lacuna", () => {
  const changed = frames();
  changed[2] = { ...changed[2], session_ms: 5000, window: "3" };
  assert.doesNotThrow(() => validateFrames(changed, 3, 10, 1000));
});
