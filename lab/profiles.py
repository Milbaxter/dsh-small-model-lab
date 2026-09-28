"""Compose released presets, preserving Cordis JavaScript YAML expressions."""
import hashlib
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARMS = ('sdk-minimal', 'standard', 'standard+autonomy-policy')


class JS(str):
    pass


class Loader(yaml.SafeLoader):
    pass


class Dumper(yaml.SafeDumper):
    pass


Loader.add_constructor('tag:yaml.org,2002:js', lambda loader, node: JS(loader.construct_scalar(node)))
Dumper.add_representer(JS, lambda dumper, value: dumper.represent_scalar('tag:yaml.org,2002:js', str(value)))


def compose(arm, run_dir, provider_rows, binary_override=None):
    if arm not in ARMS:
        raise ValueError(f'Unknown arm: {arm}')
    binary = Path(binary_override) if binary_override else ROOT / 'node_modules/.bin/dsh'
    if not binary.exists():
        raise RuntimeError('Run npm ci to install the pinned DSH CLI')
    profile = 'sdk-minimal' if arm == 'sdk-minimal' else 'sdk'
    rows = list(provider_rows)
    provenance = {'arm': arm, 'cli_version': '0.1.7-rc.2'}
    if arm != 'sdk-minimal':
        # SDK full already declares this provider. A duplicate insert is invalid.
        rows[-1] = rows[-1]['insert'][0]
        rows.append({"id": "session-persistence-jsonl", "config": {"root": JS("dshHomePath('sessions')"), "compression": "none"}})
        installed = ROOT / 'node_modules/@deepseek-ai/dsh-web-app'
        preset_path = installed / 'presets/standard.patch.yml'
        preset = yaml.load(preset_path.read_text(), Loader=Loader)
        base = yaml.load(subprocess.check_output(
            [str(binary), '--profile', 'sdk', '--dump-default-config'], text=True), Loader=Loader)
        existing = {row['id'] for row in base}
        web = yaml.load((installed / 'cordis.patch.yml').read_text(), Loader=Loader)
        rows.extend({'id': row['id'], 'disabled': True} for row in web
                    if row.get('disabled') is True and row.get('id') in existing)
        rows.append({'insert': [{'id': 'subagent-model-selection-settings',
            'name': '@deepseek-ai/dsh-tool-subagent/model-selection-settings'}]})
        rows.append({'insert': [{'id': 'agent-preset-registry',
            'name': '@deepseek-ai/dsh-agent-preset-registry', 'config': {'default': 'standard'}}]})
        # The upstream 65k headroom would disable compaction at the lab's 16k context.
        plugins = preset[0]['insert'][0]['config']['plugins']
        group = next(p for p in plugins if p['id'] == 'compaction')
        compactor = next(p for p in group['config'] if p['id'] == 'compaction-basic')
        compactor['config'] = {'headroomTokens': 1024, 'thresholdRatio': 0.75,
                               'retainTokens': 2048, 'maxTokens': 1024}
        rows.extend(preset)
        rows.append({'insert': [{'id': 'lab-sdk-standard',
            'name': str(ROOT / 'lab/plugins/standard.mjs')}]})
        provenance['upstream_standard_sha256'] = hashlib.sha256(preset_path.read_bytes()).hexdigest()
        provenance['compaction'] = compactor['config']
        if arm == 'standard+autonomy-policy':
            policy = ROOT / 'vendor/autonomy-policy/index.js'
            rows.append({'insert': [{'id': 'optimal-autonomy-policy', 'name': str(policy)}]})
            provenance['policy_sha256'] = hashlib.sha256(policy.read_bytes()).hexdigest()
    path = Path(run_dir) / 'profile.patch.yml'
    path.write_text(yaml.dump(rows, Dumper=Dumper, sort_keys=False))
    return str(binary), profile, str(path), provenance
