#!/usr/bin/env python3
import configparser
import json
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List

import pkg_resources
import pydoctor.driver
import requests
import toml

# TODO: set USER_AGENT


def fetch_package_info(package_name: str):
    return requests.get(f'https://pypi.org/pypi/{package_name}/json').json()


def find_packages(path: Path, package_name: str) -> List[Path]:
    package_name = package_name.lower()

    # we don't want to execute setup.py, so we firstly check setup.cfg

    setup_cfg = path / 'setup.cfg'
    if setup_cfg.exists():
        parser = configparser.ConfigParser()
        parser.read(setup_cfg)
        package_dir = parser.get('options', 'package_dir', fallback=None)
        if package_dir is not None:
            package_dir = package_dir.strip()
            if package_dir.startswith('='):
                package_dir = package_dir.lstrip('= ')
                # TODO: ensure path is safe
                if (path / package_dir / package_name / '__init__.py').exists():
                    return [path / package_dir / package_name]
            else:
                print("[warning] options.package_dir in setup.cfg doesn't start with =")

    # we couldn't find the package via setup.cfg so we fallback to educated guesses

    if (path / package_name / '__init__.py').exists():
        return [path / package_name]

    if (path / 'src' / package_name / '__init__.py').exists():
        return [path / 'src' / package_name]

    packages = []

    for subpath in path.iterdir():
        if subpath.is_dir():
            if (subpath / '__init__.py').exists():
                packages.append(subpath)
    return packages


if __name__ == '__main__':
    sources = Path('sources')
    sources.mkdir(exist_ok=True)

    try:
        with open('versions.json') as f:
            versions = json.load(f)
    except FileNotFoundError:
        versions: Dict[str, str] = {}

    download_dir = Path(tempfile.mkdtemp(prefix='pydoc-'))

    # 1. fetch sources

    for package_name in (
        pkg_resources.resource_string(__name__, 'packages.txt').decode().splitlines()
    ):
        package = fetch_package_info(package_name)
        version = package['info']['version']

        sourceid = f'{package_name}-{version}'

        if (
            package_name not in versions
            or versions[package_name] != version
            or not (sources / sourceid).exists()
        ):
            print('downloading', sourceid)

            source_packages = [
                p for p in package['releases'][version] if p['packagetype'] == 'sdist'
            ]
            assert len(source_packages) > 0

            if len(source_packages) > 1:
                print(
                    f"[warning] {package_name} returned multiple source distributions, we're just using the first one"
                )

            source_package = source_packages[0]

            filename = source_package['filename']
            assert '/' not in filename  # for security

            archive_path = download_dir / filename

            with requests.get(source_package['url'], stream=True) as r:
                with open(archive_path, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)

            if filename.endswith('.tar.gz'):
                tf = tarfile.open(archive_path)
                for member in tf.getmembers():
                    # TODO: check that path is secure (doesn't start with /, doesn't contain ..)
                    if '/' in member.name:
                        member.name = member.name.split('/', maxsplit=1)[1]
                    else:
                        member.name = '.'
                tf.extractall(sources / sourceid)
            elif filename.endswith('.zip'):
                with zipfile.ZipFile(archive_path) as zf:
                    for info in zf.infolist():
                        # TODO: check that path is secure (doesn't start with /, doesn't contain ..)
                        if '/' in info.filename.rstrip('/'):
                            info.filename = info.filename.split('/', maxsplit=1)[1]
                        else:
                            info.filename = './'
                        zf.extract(info, sources / sourceid)
            else:
                print('[error] unknown source dist archive format', filename)

            versions[package_name] = version

    with open('versions.json', 'w') as f:
        json.dump(versions, f)

    shutil.rmtree(download_dir)

    with open('overrides.toml') as f:
        overrides = toml.load(f)

    # 2. generate docs with pydoctor

    dist = Path('dist')
    dist.mkdir(exist_ok=True)

    for path in sources.iterdir():
        sourceid = path.name
        package_name, version = sourceid.rsplit('-', maxsplit=1)

        packages = list(find_packages(sources / sourceid, package_name))

        if len(packages) == 0:
            print(
                '[error] failed to determine package directory for', sources / sourceid
            )
            continue

        if len(packages) > 1:
            print(
                f"[warning] found multiple packages for {package_name} ({packages}), we're just using the first one"
            )

        docformat = overrides['docformat'].get(package_name, 'restructuredtext')

        out_dir = dist / package_name / version

        if out_dir.exists():
            continue

        print('generating', sourceid)

        out_dir.mkdir(parents=True)
        pydoctor.driver.main(
            # fmt: off
            [
                str(packages[0]),
                '--html-output', out_dir,
                '--docformat', docformat,
            ]
            # fmt: on
        )

    # 3. create latest symlinks
    for package_name, version in versions.items():
        latest = dist / package_name / 'latest'
        latest.unlink(missing_ok=True)
        latest.symlink_to(version)
