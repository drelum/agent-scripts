import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { frameSeekTime } from "./video-time.ts";

void test("seek fica dentro do frame real, inclusive PTS arredondado na troca de aba", (context) => {
  const folder = mkdtempSync(join(tmpdir(), "posthog-video-time-"));
  context.after(() => rmSync(folder, { recursive: true }));
  const file = join(folder, "fixture.mp4");
  execFileSync(
    "ffmpeg",
    [
      "-v",
      "error",
      "-f",
      "lavfi",
      "-i",
      "color=red:s=64x64:r=12:d=4",
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      file,
    ],
    { stdio: "pipe" },
  );
  const probe = JSON.parse(
    execFileSync(
      "ffprobe",
      [
        "-v",
        "error",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp_time",
        "-of",
        "json",
        file,
      ],
      { encoding: "utf8" },
    ),
  );
  const pts = probe.frames.map((frame) => Number(frame.best_effort_timestamp_time));
  const displayed = (time) => pts.findLastIndex((value) => value <= time);
  assert.equal(displayed(35 / 12), 34); // Defeito reproduzido com o encoder real.
  for (let i = 0; i < pts.length; i++) {
    const target = frameSeekTime(i, 12);
    assert.equal(displayed(target), i);
    assert.equal(Math.floor(target * 12), i);
  }
});
