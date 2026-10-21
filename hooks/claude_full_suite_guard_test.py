#!/usr/bin/env python3
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from claude_full_suite_guard import find_broad_run  # noqa: E402

CWD = "/repo"


class FindBroadRunTest(unittest.TestCase):
    def assertBroad(self, command, project=CWD):
        self.assertEqual(find_broad_run(command, CWD), project, command)

    def assertAllowed(self, command):
        self.assertIsNone(find_broad_run(command, CWD), command)

    def test_barra_suite_inteira(self):
        self.assertBroad("pnpm test")
        self.assertBroad("pnpm run test")
        self.assertBroad("VITEST_MAX_WORKERS=3 pnpm test --project=unit --project=aura-client-js")
        self.assertBroad("pnpm test --project unit --maxWorkers 3")
        self.assertBroad("pnpm exec vitest run --maxWorkers=3 --silent")
        self.assertBroad("npx vitest")
        self.assertBroad("node node_modules/vitest/vitest.mjs run --project=unit")
        self.assertBroad("vp test")
        self.assertBroad("bunx vitest run")
        self.assertBroad("bun --bun node_modules/vitest/vitest.mjs run")
        self.assertBroad("pnpm exec vitest run -t 'carrinho'")
        self.assertBroad("pnpm test > /tmp/x.log 2>&1")

    def test_resolve_diretorio_do_projeto(self):
        self.assertBroad("cd aura-ui && pnpm test", "/repo/aura-ui")
        self.assertBroad("pnpm -C /outro test", "/outro")
        self.assertBroad("cd /x && pnpm lint && pnpm test 2>&1 | tail -5", "/x")

    def test_libera_selecao_e_intencao(self):
        self.assertAllowed("FULL_SUITE=1 pnpm test --project=unit")
        self.assertAllowed("pnpm test:changed")
        self.assertAllowed("pnpm exec vitest run --changed")
        self.assertAllowed("pnpm exec vitest run --changed=origin/main")
        self.assertAllowed("pnpm exec vitest related --run src/shared/a.ts")
        self.assertAllowed("pnpm exec vitest run src/modules/cart")
        self.assertAllowed("pnpm test --project=unit src/modules/cart/x.test.tsx")
        self.assertAllowed("pnpm exec vitest --help")
        self.assertAllowed("pnpm test:e2e")
        self.assertAllowed("pnpm typecheck && pnpm lint")
        self.assertAllowed("git push -u origin feat/x")
        self.assertAllowed("cat vitest.config.ts")
        self.assertAllowed("ls node_modules/vitest")
        self.assertAllowed("rg vitest")
        self.assertAllowed("grep -n vitest package.json")
        self.assertAllowed("pnpm exec vitest run src/a.test.ts > /tmp/x.log 2>&1")


if __name__ == "__main__":
    unittest.main()
