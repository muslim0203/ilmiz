"""Package source-only updates. No databases, environment files or credentials."""
import argparse
import hashlib
import tarfile
from pathlib import Path


PUBLIC_DEPLOY_FILES = {
    'check_repository.py', 'package_runtime.py', 'prepare_staging.py',
    'requirements-ovh-20260831.txt', 'runtime-constraints.txt',
    'test_prepare_staging.py', 'test_repository_guard.py',
    'ci_deploy.py', 'test_ci_deploy.py',
    # OAI-PMH harvest jadvali (systemd timer) va uni o'rnatuvchi skript.
    'ilmiz-harvest.service', 'ilmiz-harvest.timer',
    'ilmiz-harvest-retry.service', 'ilmiz-harvest-retry.timer',
    'install_harvest_timer.sh',
    # Serverdagi kodni arxiv bilan yangilash (zaxira, test, rollback).
    'update_app.sh',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if not (root / 'dist/index.html').is_file():
        raise SystemExit('Run npm run build first.')
    args.output.mkdir(parents=True, exist_ok=False)
    files = list((root / 'backend').rglob('*.py')) + list((root / 'harvester').rglob('*.py'))
    files += [root / 'backend/requirements.txt']
    # `init_db()` migratsiyalar uchun ildizdagi alembic.ini ni o'qiydi;
    # usiz yangi serverda xizmat startda yiqiladi.
    files += [root / 'alembic.ini']
    files += [p for p in (root / 'dist').rglob('*') if p.is_file()]
    files += [root / 'deploy' / name for name in PUBLIC_DEPLOY_FILES]
    assert root / 'harvester/oai_harvester.py' in files
    target = args.output / 'runtime.tar.gz'
    with tarfile.open(target, 'x:gz') as archive:
        for path in sorted(files):
            assert not path.is_symlink()
            assert not any(part.startswith('.') for part in path.relative_to(root).parts)
            archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
    with target.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    (args.output / 'SHA256SUMS').write_text(f'{digest}  runtime.tar.gz\n', encoding='ascii')
    print(f'{target}: {target.stat().st_size} bytes; SHA256 {digest}')


if __name__ == '__main__':
    main()
