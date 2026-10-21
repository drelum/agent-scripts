const { test } = require("node:test");
const assert = require("node:assert/strict");
const { gzipSync, zstdCompressSync } = require("node:zlib");
const { prepare, planExperiment } = require("./private/core.cjs");
const { chooseWindow } = require("./private/frame.cjs");
const node = { type: 0, id: 1, childNodes: [] };
const meta = {
  type: 4,
  timestamp: 1000,
  data: { href: "https://example.test/", width: 100, height: 100 },
};
const full = { type: 2, timestamp: 1001, data: { node, initialOffset: { top: 0, left: 0 } } };
const text = (events) => events.map((event) => JSON.stringify(["w", event])).join("\n");
void test("selected overlapping tab remains selected and gaps are refused", () => {
  const tabs = [
    { id: "1", start: 0, end: 100 },
    { id: "2", start: 50, end: 150 },
  ];
  assert.equal(chooseWindow(tabs, 75, "2").id, "2");
  assert.equal(chooseWindow(tabs, 80, "2").id, "2");
  assert.equal(chooseWindow(tabs, 75).id, "1");
  assert.equal(chooseWindow(tabs, 151, "2"), undefined);
});

void test("upstream gzip decompresses full snapshot and refuses unknown codecs", async () => {
  const compressed = {
    ...full,
    cv: "2024-10",
    data: gzipSync(JSON.stringify(full.data)).toString("latin1"),
  };
  const result = await prepare(text([meta, compressed]));
  assert.equal(result.window_id_map.w, 1);
  assert.deepEqual(result.events.find((e) => e.type === 2).data.node, node);
  await assert.rejects(prepare(text([meta, { ...compressed, cv: "future" }])));
  await assert.rejects(prepare(text([meta, { ...compressed, data: "corrupt" }])));
});
void test("malformed line cannot become an apparently complete recording", async () => {
  await assert.rejects(prepare(text([meta, full]) + "\ninvalid-json"));
});
void test("flat string window IDs keep Meta and full snapshot in the same mapped tab", async () => {
  const uuid = "00000000-0000-0000-0000-000000000001";
  const flat = [meta, full].map((event) => JSON.stringify({ ...event, windowId: uuid })).join("\n");
  const result = await prepare(flat);
  assert.equal(result.window_id_map[uuid], 1);
  assert.deepEqual([...new Set(result.events.map((event) => event.windowId))], [1]);
  assert.equal(result.events.filter((event) => event.type === 2).length, 1);
});
void test("upstream zstd decompresses without losing the snapshot", async () => {
  const compressed = {
    ...full,
    cv: "2024-10",
    data: zstdCompressSync(JSON.stringify(full.data)).toString("latin1"),
  };
  const result = await prepare(text([meta, compressed]));
  assert.deepEqual(result.events.find((e) => e.type === 2).data.node, node);
});
void test("planner fetches preceding snapshot and all intervening sources in correct window", () => {
  const events = [
    { ...meta, windowId: 1 },
    { ...full, windowId: 1 },
  ];
  for (let i = 2; i < 1600; i++)
    events.push({
      type: 3,
      timestamp: 1000 + i,
      windowId: 1,
      data: { source: 3, id: 1, x: i, y: 0 },
    });
  const plan = planExperiment(events, 2100, 1);
  assert.equal(plan.playable, true);
  assert.ok(plan.batches.some((b) => ["seek_backward", "seek_gap_fill"].includes(b.reason)));
  assert.ok(plan.loaded_sources >= 12);
  assert.equal(planExperiment(events, 2100, 2).playable, false);
});
