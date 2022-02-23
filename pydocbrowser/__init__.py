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
from typing import Any, Dict, List, cast

import importlib_resources
import jinja2
import mistletoe
import pydoctor.driver
import requests
import toml

# TODOs: 
# - Use argparse and make the path to packages.toml configurable
# - Generate a index of versions per packages and link to that from the header
# - Automatically create pull request every day including 10 new libraries 
#       https://peterevans.dev/posts/github-actions-how-to-create-pull-requests-automatically/
# - 

def fetch_package_info(package_name: str) -> Dict[str, Any]:
    return cast('Dict[str, Any]', requests.get(f'https://pypi.org/pypi/{package_name}/json',
        headers={'User-Agent': 'pydocbrowser/pydocbrowser'}).json())

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

EXTRA_CSS = (importlib_resources.files('pydocbrowser') / 
                                        'pydoctor_templates' / 
                                        'extra.css').read_text()
HEADER_HTML = (importlib_resources.files('pydocbrowser') / 
                                        'pydoctor_templates' / 
                                        'header.html').read_text()

def main() -> None:
    sources = Path(SOURCES)
    sources.mkdir(exist_ok=True, parents=True)

    versions: Dict[str, str] = {}
    try:
        with open(VERSIONS) as f:
            versions.update(json.load(f))
    except FileNotFoundError:
         pass

    download_dir = Path(tempfile.mkdtemp(prefix='pydocbrowser-'))

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
                with open(archive_path, 'wb') as f: #type:ignore[assignment]
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
                raise RuntimeError(f'unknown python source dist archive format: {filename}')

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

        out_dir = dist / package_name / version

        if out_dir.exists():
            continue

        out_dir.mkdir(parents=True)

        # preparing the pydoctor templates
        pydoctor_templates_dir = Path(tempfile.mkdtemp(prefix='pydocbrowser-'))
        with (pydoctor_templates_dir / 'extra.css').open('w') as fob:
            fob.write(EXTRA_CSS)
        with (pydoctor_templates_dir / 'header.html').open('w') as fob:
            fob.write(HEADER_HTML.replace("<!-- sourceid -->", f"> {sourceid}"))

        _f = io.StringIO()
        with contextlib.redirect_stdout(_f):
            pydoctor.driver.main(
                packages[package_name].get('pydoctor_args', []) + 
                [
                    f'--html-output={out_dir}',
                    f'--template-dir={pydoctor_templates_dir}', 
                    f'--project-base-dir={sources/sourceid}',
                    f'--html-viewsource-base=https://github.com/pydocbrowser/pydocbrowser.github.io/tree/main/build/sources/{sourceid}/',
                    '--intersphinx=https://docs.python.org/3/objects.inv', 
                    '--quiet', 
                    str(package_paths[0]),
                ],
            )
        
        shutil.rmtree(pydoctor_templates_dir.as_posix())

        _pydoctor_output = _f.getvalue()
        print(f'{sourceid}: {len(_pydoctor_output.splitlines())} warnings')

    # 3. create latest symlinks
    for package_name, version in versions.items():
        if package_name not in packages:
            continue
        latest = dist / package_name / 'latest'
        try:
            latest.unlink(missing_ok=True)
        except IsADirectoryError:
            # Github transform symlink to actual directories it seem...
            shutil.rmtree(latest.as_posix())
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
                header=HEADER_HTML,
                before=before,
                packages=package_infos.items(),
                after=after,
            )
        )
    with open(dist / 'extra.css', 'w') as f:
        f.write(EXTRA_CSS)
