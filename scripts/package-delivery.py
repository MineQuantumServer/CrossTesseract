#!/usr/bin/env python3
"""Package explicit project/evidence paths; exclude worlds, credentials and upstream binaries."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.1.0-dev'
OUTPUT = ROOT / 'build/distributions'
ROOT_FILES = (
    '.gitignore', 'LICENSE', 'README.md', 'settings.gradle', 'build.gradle',
    'gradle.properties', 'gradle.lockfile', 'gradlew', 'gradlew.bat',
)


def files(directory):
    for path in (ROOT / directory).rglob('*'):
        if path.is_symlink():
            raise RuntimeError('Refusing a symlink in delivery: ' + str(path))
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            yield path


def package(name, paths):
    destination = OUTPUT / name
    inventory = sorted(set(paths))
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        for path in inventory:
            if not path.is_file() or path.is_symlink():
                raise RuntimeError('Missing/unsafe file: ' + str(path))
            relative = path.relative_to(ROOT)
            if any(part in ('.git', '.gradle', 'scratch', 'shared', 'volumes')
                   or part.startswith('run-') for part in relative.parts):
                raise RuntimeError('Forbidden delivery path: ' + str(relative))
            if relative.name == '.env' or relative.name.endswith('.local.properties'):
                raise RuntimeError('Credential file in delivery: ' + str(relative))
            archive.write(path, str(relative))
    with zipfile.ZipFile(destination) as archive:
        bad_entry = archive.testzip()
        if bad_entry is not None:
            raise RuntimeError('Corrupt archive entry: ' + bad_entry)
    return {
        'path': str(destination.relative_to(ROOT)),
        'bytes': destination.stat().st_size,
        'sha256': hashlib.file_digest(destination.open('rb'), 'sha256').hexdigest(),
        'entries': len(inventory),
    }


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    reports = [p for p in files('reports')
               if 'raw' not in p.relative_to(ROOT / 'reports').parts
               and p.name != 'delivery-artifacts.json']
    project = [ROOT / name for name in ROOT_FILES]
    for directory in ('src', 'docs', 'scripts', 'config', 'gradle'):
        project.extend(files(directory))
    project += [ROOT / 'deploy/compose.dev.yml'] + reports
    project += sorted((ROOT / 'build/libs').glob('cross_tesseract-' + VERSION + '*.jar'))
    if len([p for p in project if p.suffix == '.jar' and p.parent.name == 'libs']) != 2:
        raise RuntimeError('Expected the binary and sources JARs')
    evidence = [p for p in files('reports') if p.name != 'delivery-artifacts.json']
    for directory in ('logs', 'build/test-results/test', 'build/reports/tests/test', 'docs'):
        evidence.extend(files(directory))
    result = {
        'utc': datetime.now(timezone.utc).isoformat(),
        'version': VERSION,
        'command': 'python3 scripts/package-delivery.py',
        'artifacts': [
            package('cross_tesseract-' + VERSION + '-project.zip', project),
            package('cross_tesseract-' + VERSION + '-test-evidence.zip', evidence),
        ],
        'exclusions': ['worlds', 'database volumes', 'credentials files',
                       'upstream repositories/runtime mods', 'Minecraft/NeoForge binaries',
                       'JDK', 'Gradle cache', 'user files'],
    }
    (ROOT / 'reports/delivery-artifacts.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
