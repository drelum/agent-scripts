// Build autocontido: fontes PostHog fixadas e verificadas antes de compilar.
import { build } from "esbuild";
import { resolve } from "node:path";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { verifyVendor } from "./vendor-proof.mjs";
const root = import.meta.dirname;
const upstream = verifyVendor(resolve(root, "vendor/posthog"));
mkdirSync(resolve(root, "private"), { recursive: true, mode: 0o700 });
const options = {
  bundle: true,
  nodePaths: [resolve(root, "node_modules")],
  alias: { "@posthog/replay-shared": resolve(root, "vendor/posthog/replay-shared/src/index.ts") },
  target: "es2020",
};
for (const entry of ["headless", "investigator", "player"]) {
  await build({
    ...options,
    entryPoints: [resolve(root, `${entry}.ts`)],
    outfile: resolve(root, `private/${entry}.js`),
    platform: "browser",
    format: "iife",
    minify: true,
    define: { "process.env.NODE_ENV": '"production"', "process.env": "{}" },
  });
}
for (const entry of ["frame", "core"]) {
  await build({
    ...options,
    entryPoints: [resolve(root, `${entry}.ts`)],
    outfile: resolve(root, `private/${entry}.cjs`),
    platform: "node",
    format: "cjs",
  });
}
const files = ["player.js", "core.cjs", "headless.js", "investigator.js", "frame.cjs"];
writeFileSync(
  resolve(root, "private/build.json"),
  JSON.stringify(
    {
      upstream_commit: upstream.commit,
      upstream_hashes: upstream.files,
      hashes: Object.fromEntries(
        files.map((file) => [
          file,
          createHash("sha256")
            .update(readFileSync(resolve(root, "private", file)))
            .digest("hex"),
        ]),
      ),
    },
    null,
    2,
  ),
);
