import { defineConfig } from "vite-plus";
export default defineConfig({
  lint: {
    options: { typeAware: true, typeCheck: true },
    ignorePatterns: ["private/**", "vendor/**"],
  },
  fmt: { ignorePatterns: ["private/**", "vendor/**", "node_modules/**"] },
});
