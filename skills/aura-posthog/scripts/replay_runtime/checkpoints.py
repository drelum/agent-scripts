"""Fases locais retomáveis; configuração e bytes conferidos antes do reuso."""
from pathlib import Path

import bundles
import lab


class Checkpoints:
    def __init__(self, name, config):
        self.stage = lab.PRIVATE / 'packages-staging' / name
        path = self.stage / 'checkpoint.json'
        if path.exists():
            self.state = bundles.read(path)
            if self.state.get('config') != config:
                raise ValueError('Checkpoint de outra configuração/versão; usar nome novo. Evidências preservadas.')
        else:
            if self.stage.exists():
                raise ValueError('Staging sem checkpoint; preservado para diagnóstico. Usar nome novo.')
            self.stage.mkdir(parents=True, mode=0o700)
            self.state = {'schema': 1, 'config': config, 'phases': {}}
            lab.write_json(path, self.state)

    def read(self, phase):
        item = self.state['phases'].get(phase)
        if item is None:
            return None
        for name, digest in item['files'].items():
            path = Path(name)
            if path.is_absolute() or '..' in path.parts or bundles.sha(lab.PRIVATE / path) != digest:
                raise ValueError(f'Checkpoint {phase} corrompido; evidência preservada.')
        return item['value']

    def save(self, phase, value, files):
        self.state['phases'][phase] = {'value': value,
            'files': {str(path.relative_to(lab.PRIVATE)): bundles.sha(path) for path in files}}
        lab.write_json(self.stage / 'checkpoint.json', self.state)

    def begin(self, phase):
        self.state['active_phase'] = phase
        lab.write_json(self.stage / 'checkpoint.json', self.state)

    def collect(self, phase, function):
        self.begin(phase)
        cached = self.read(phase)
        if cached is not None:
            print(f'{self.stage.name}: retomada da fase {phase}', flush=True)
            return bundles.read(self.stage / f'{phase}-checkpoint.json')
        value = function()
        path = self.stage / f'{phase}-checkpoint.json'
        lab.write_json(path, value)
        self.save(phase, {'ready': True}, [path])
        return value
