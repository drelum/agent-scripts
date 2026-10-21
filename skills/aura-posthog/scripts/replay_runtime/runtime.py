"""Instalação e diagnóstico explícitos; sem downloads de browser ou acesso a sessões."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def analysis_python():
    executable = ROOT / 'private/analysis-venv/bin/python'
    if not executable.is_file():
        raise ValueError('Dependências Gemini ausentes; executar replay_investigate setup.')
    return executable


def setup_analysis():
    # --without-pip funciona no WSL mesmo quando ensurepip não está instalado.
    target = ROOT / 'private/analysis-venv'
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(target)], check=True)
    subprocess.run([sys.executable, '-m', 'pip', '--python', str(target / 'bin/python'),
                    'install', '-r', str(ROOT / 'analysis-requirements.txt')], check=True)


def analysis_ready():
    try:
        subprocess.run([str(analysis_python()), '-c', 'import jinja2,jsonschema'],
                       check=True, capture_output=True, timeout=15)
        return True
    except (ValueError, OSError, subprocess.SubprocessError):
        return False


def check_binary(name, argument='-version'):
    executable = shutil.which(name)
    if not executable:
        return False
    try:
        subprocess.run([executable, argument], check=True, capture_output=True, timeout=15)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def prerequisites():
    node = shutil.which('node')
    try:
        version = subprocess.check_output([node, '--version'], text=True, timeout=15) if node else ''
        node_ok = int(version.lstrip('v').split('.')[0]) >= 24
    except (ValueError, OSError, subprocess.SubprocessError):
        node_ok = False
    chrome = os.environ.get('PUPPETEER_EXECUTABLE_PATH')
    chrome_ok = bool(chrome and Path(chrome).is_absolute() and os.access(chrome, os.X_OK))
    if chrome_ok:
        try:
            subprocess.run([chrome, '--version'], check=True, capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            chrome_ok = False
    return {'node_24': node_ok, 'npm': check_binary('npm', '--version'),
            'ffmpeg': check_binary('ffmpeg'), 'ffprobe': check_binary('ffprobe'),
            'chrome_configured': chrome_ok, 'posthog_cli': bool(shutil.which('posthog-cli'))}


def capture_preflight():
    try:
        result = subprocess.run(['node', str(ROOT / 'browser.mjs')],
                                capture_output=True, text=True, timeout=40)
        return result.returncode == 0 and json.loads(result.stdout).get('ready') is True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def require_capture():
    if not capture_preflight():
        raise ValueError('Pré-teste de captura falhou: configurar chrome-headless-shell em PUPPETEER_EXECUTABLE_PATH; executar doctor. Nenhuma sessão foi coletada.')


def doctor():
    checks = prerequisites()
    checks['dependencies'] = (ROOT / 'node_modules/esbuild/package.json').is_file()
    checks['analysis_dependencies'] = analysis_ready()
    checks['chrome_capture'] = capture_preflight()
    try:
        manifest = json.loads((ROOT / 'private/build.json').read_text())
        checks['build'] = all(hashlib.sha256((ROOT / 'private' / name).read_bytes()).hexdigest() == sha
                              for name, sha in manifest['hashes'].items())
        checks['build'] = checks['build'] and all(name in manifest['hashes']
                          for name in ('core.cjs', 'headless.js', 'investigator.js'))
    except (OSError, ValueError, KeyError, TypeError):
        checks['build'] = False
    return {'ready': all(checks.values()), 'checks': checks}


def setup():
    checks = prerequisites()
    if not checks['node_24'] or not checks['npm']:
        raise ValueError('Instalação exige Node 24+ e npm no PATH.')
    subprocess.run(['npm', 'ci', '--ignore-scripts'], cwd=ROOT, check=True)
    subprocess.run(['npm', 'run', 'build'], cwd=ROOT, check=True)
    setup_analysis()
    report = doctor()
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['ready'] else 1
