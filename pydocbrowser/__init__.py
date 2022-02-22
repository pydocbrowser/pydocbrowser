#!/usr/bin/env python3
import configparser
import json
import shutil
import sys
import contextlib
import io
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List

import jinja2
import mistletoe
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

    if (path / (package_name + '.py')).exists():
        # single-file package (e.g. Bottle)
        return [path / (package_name + '.py')]

    packages = []

    for subpath in path.iterdir():
        if subpath.is_dir():
            if (subpath / '__init__.py').exists():
                packages.append(subpath)
    return packages

SOURCES = 'build/sources'
VERSIONS = 'build/versions.json'
WWW = 'build/www'
README = 'README.md'
PACKAGES = 'packages.toml'

def main():
    sources = Path(SOURCES)
    sources.mkdir(exist_ok=True)

    try:
        with open(VERSIONS) as f:
            versions = json.load(f)
    except FileNotFoundError:
        versions: Dict[str, str] = {}

    download_dir = Path(tempfile.mkdtemp(prefix='pydoc-'))

    # 1. fetch sources

    print('fetching sources...')
    package_infos = {}

    with open(PACKAGES) as f:
        packages = toml.load(f)

    for package_name in packages:
        package = fetch_package_info(package_name)
        package_infos[package_name] = package
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

    with open(VERSIONS, 'w') as f:
        json.dump(versions, f)

    shutil.rmtree(download_dir)

    # 2. generate docs with pydoctor

    print('generating docs...')
    dist = Path(WWW)
    dist.mkdir(exist_ok=True)

    for package_name in list(packages):
        version = versions[package_name]
        sourceid = f'{package_name}-{version}'
        if not (sources / sourceid).exists():
            continue

        package_paths = list(find_packages(sources / sourceid, package_name))

        if len(package_paths) == 0:
            print(
                '[error] failed to determine package directory for', sources / sourceid
            )
            continue

        if len(package_paths) > 1:
            print(
                f"[warning] found multiple packages for {package_name} ({package_paths}), we're just using the first one"
            )

        docformat = packages[package_name].get('docformat', 'restructuredtext')

        out_dir = dist / package_name / version

        if out_dir.exists():
            continue

        out_dir.mkdir(parents=True)

        _f = io.StringIO()
        with contextlib.redirect_stdout(_f):
            pydoctor.driver.main(
                [
                    str(package_paths[0]),
                    '--html-output', out_dir,
                    '--docformat', docformat,
                    '--quiet',
                ],
            )

        _pydoctor_output = _f.getvalue()
        print(f'{sourceid}: {len(_pydoctor_output.splitlines())} warnings')

    # 3. create latest symlinks
    for package_name, version in versions.items():
        if package_name not in packages:
            continue
        latest = dist / package_name / 'latest'
        latest.unlink(missing_ok=True)
        latest.symlink_to(version)

    # 4. create start page
    env = jinja2.Environment(
        loader=jinja2.PackageLoader("pydocbrowser"), autoescape=True)

    readme_html = mistletoe.markdown(
        Path(README).read_text()
    )

    sep = '<!-- package list -->'
    
    try:
        before, after = readme_html.split(sep)
    except ValueError:
        sys.exit(f'[fatal error] expected {sep} in README.md')

    with open(dist / 'index.html', 'w') as f:
        f.write(
            env.get_template('index.html').render(
                before=before,
                packages=package_infos.items(),
                after=after,
            )
        )
