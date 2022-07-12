#!/usr/bin/env python3
import argparse
import configparser
import json
import shutil
import sys
import contextlib
import io
import os
import tarfile
import tempfile
import zipfile
import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, cast

import importlib_resources
import jinja2
import mistletoe
import pydoctor.driver
import requests
import toml

# TODOs: 
# - Generate a index of versions per packages and link to that from the header
# - Automatically create pull request every day including X new libraries 
#       https://peterevans.dev/posts/github-actions-how-to-create-pull-requests-automatically/
# - Build iteratively the docs in order to be able to scale this to the size of many projects.
#    Keepp in mind github CI limitation which is 6hours per job maximum.
#    It could work by using the github API to launch a new build after 2 hours of docs building.
#    WIP...
# - Include a very simple search bar in the index.html
# - Add indications to add a library to the system
# - Re-generate all latest documentations when we detect that the documentation have been 
#   generated with an older pydoctor version. Needs iterative build.

README = 'README.md'
PACKAGES = 'packages.toml'
PACKAGES_DEFAULT = object()

BUILD = 'build'
SOURCES = 'sources'
VERSIONS = 'versions.json'
WWW = 'www'

BUILD_TIMEOUT = 120

EXTRA_CSS = (importlib_resources.files('pydocbrowser') / 
                                        'pydoctor_templates' / 
                                        'extra.css').read_text()
HEADER_HTML = (importlib_resources.files('pydocbrowser') / 
                                        'pydoctor_templates' / 
                                        'header.html').read_text()

def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
                            description="pydocbrowser builder cli", 
                            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--config-file', metavar="PATH", dest='config_file',
                        help="Main configuration file. Ignored if option --package is passed.", 
                        type=Path, default=PACKAGES_DEFAULT)
    parser.add_argument('--readme-file', metavar="PATH", dest='readme_file',
                        help="Readme file.", 
                        type=Path, default=README)
    parser.add_argument('--build-dir', metavar="PATH", dest='build_dir',
                        help="Build directory.", 
                        type=Path, default=BUILD)
    parser.add_argument('--build-timeout', metavar="MINUTES", dest='build_timeout',
                        help="Build timeout, in minutes.", 
                        type=int, default=BUILD_TIMEOUT)
    parser.add_argument('--package', metavar="PACKAGE", 
                        help="Builds the selected package from PyPI, can repeat to build multiple packages. "
                                "Using this option makes the builder ignore the config file. "
                                "This option is designed to test pydoctor's builder, "
                                "so it uses the plaintext markup for focus on AST warnings. ", 
                        action='append', default=None, dest='packages')
    parser.add_argument('--verbose', action='store_true', dest='verbose',
                        help="Print pydoctor output", default=False)
    return parser

class Options(argparse.Namespace):
    config_file: Optional[Path]
    readme_file: Path
    build_dir: Path
    build_timeout: int
    packages: Optional[List[str]]
    verbose: bool

INTERSPHINX_URL_TEMPLATE = "https://pydocbrowser.github.io/%s/latest/objects.inv"

def generate_intersphinx_args(packages: Iterable[str]) -> Iterator[str]:
    for p in packages:
        yield '--intersphinx=' + INTERSPHINX_URL_TEMPLATE%p

def fetch_package_info(package_name: str) -> Dict[str, Any]:
    return cast('Dict[str, Any]', requests.get(f'https://pypi.org/pypi/{package_name}/json',
        headers={'User-Agent': 'pydocbrowser/pydocbrowser'}).json())

def fetch_source(package_name:str, 
                 current_version: Optional[str], 
                 sources: Path) -> Dict[str, Any]:
    """
    Download a package sources if we don't already have them on disk.

    Returns the package infos as returned by fetch_package_info.
    """
    package_info = fetch_package_info(package_name)
    version = package_info['info']['version']

    sourceid = f'{package_name}-{version}'

    if (
        current_version is None
        or current_version != version
        or not (sources / sourceid).exists()
    ):
        print('[-] downloading', sourceid)

        source_packages = [
            p for p in package_info['releases'][version] if p['packagetype'] == 'sdist'
        ]
        assert len(source_packages) > 0

        if len(source_packages) > 1:
            print(
                f"[!] {package_name} returned multiple source distributions, we're just using the first one"
            )

        source_package = source_packages[0]

        filename = source_package['filename']
        assert '/' not in filename  # for security

        download_dir = Path(tempfile.mkdtemp(prefix='pydocbrowser-'))
        try:
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
        
        finally:
            shutil.rmtree(download_dir.as_posix())
    
    return package_info

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
                print(f"[!] options.package_dir in {package_name}'s setup.cfg doesn't start with =")

    # TODO: Parse the AST of setup.py and extract packages list

    # we couldn't find the package via setup.cfg so we fallback to educated guesses
    # TODO: ensure this behaves likes find_packages()

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
    
    # Filter 'test' and 'tests' packages
    packages = [p for p in packages if p.name not in ['test', 'tests']]
    
    return packages

def run_pydoctor(package_name:str, 
                    version: str, 
                    sources: Path, 
                    dist: Path, 
                    args: List[str],
                    verbose: bool=False) -> int:

    sourceid = f'{package_name}-{version}'
    
    if not (sources / sourceid).exists():
        print(f'[!] missing source code for {sourceid}')
        return -1
    
    out_dir = dist / package_name / version
    if out_dir.exists():
        # Already built docs
        # TODO: Check if version of pydoctor that built the docs is an older version, 
        #   rebuilds the docs to use latest pydoctor.
        #   Look for tag <meta name="generator" content="pydoctor 22.2.0">  in the index.html
        #   We should de a bit of refactoring before that.
        print(f'[-] already built docs for {sourceid}')
        return 0

    package_paths = list(find_packages(sources / sourceid, package_name))

    if len(package_paths) == 0:
        print(
            '[!] failed to determine package directory for', sources / sourceid
        )
        return -1

    if len(package_paths) > 1:
        print(
            f"[!] found multiple packages for {package_name} ({package_paths}), we're just using the first one"
        )

    out_dir.mkdir(parents=True)

    # preparing the pydoctor templates
    pydoctor_templates_dir = Path(tempfile.mkdtemp(prefix='pydocbrowser-'))
    with (pydoctor_templates_dir / 'extra.css').open('w') as fob:
        fob.write(EXTRA_CSS)
    with (pydoctor_templates_dir / 'header.html').open('w') as fob:
        fob.write(HEADER_HTML.replace("<!-- sourceid -->", f"> {sourceid}"))
        
    # generating args
    _args = args + [
                f'--html-output={out_dir}',
                f'--template-dir={pydoctor_templates_dir}', 
                f'--project-base-dir={sources/sourceid}',
                f'--html-viewsource-base=https://github.com/pydocbrowser/pydocbrowser.github.io/tree/main/build/sources/{sourceid}/',
                '--intersphinx=https://docs.python.org/3/objects.inv', 
                '--quiet', 
                str(package_paths[0]),
            ]
    
    print(f"[-] running 'pydoctor [...] {package_paths[0]}'")
    
    _f = io.StringIO()

    code:int = -1
    with contextlib.redirect_stdout(_f):
        code = pydoctor.driver.main(_args)
    
    shutil.rmtree(pydoctor_templates_dir.as_posix())

    _pydoctor_output = _f.getvalue()
    nb_warnings = len(_pydoctor_output.splitlines())
    print(f'[-] {sourceid}: {nb_warnings} warnings')
    if verbose and nb_warnings>0:
        print(_pydoctor_output)
    return code

def post_process_options(options: Options) -> None:
    if options.packages:
        if options.config_file != PACKAGES_DEFAULT:
            print("[!] config file ignored because option --package is used.")
        options.config_file = None
    elif options.config_file == PACKAGES_DEFAULT:
        options.config_file = Path(PACKAGES)

def main(args: Sequence[str] = sys.argv[1:]) -> int:
    _exit_code = 0

    options = cast(Options, get_parser().parse_args(args))
    post_process_options(options)

    _build_start_time = datetime.datetime.now()
    _build_timeout = datetime.timedelta(minutes=options.build_timeout)

    sources = options.build_dir / SOURCES
    sources.mkdir(exist_ok=True, parents=True)

    versions: Dict[str, str] = {}
    try:
        with (options.build_dir / VERSIONS).open() as f:
            versions.update(json.load(f))
    except FileNotFoundError:
         pass

    # 1. fetch sources

    print('[+] fetching sources...')
    package_infos = {}
    
    # Figure the packages list we want to build the documentation for
    if options.config_file:
        with options.config_file.open() as f:
            packages = toml.load(f)
        for pack in packages.values():
            if isinstance(pack, dict):
                if 'pydoctor_args' not in pack:
                    pack['pydoctor_args'] = []
                # Use plaintext docformat by default
                if not any ('--docformat' in arg for arg in pack['pydoctor_args']):
                    pack['pydoctor_args'].append('--docformat=plaintext')
    else:
        assert options.packages is not None
        packages = { p:{ 'pydoctor_args':
            [
                '--docformat=plaintext', 
                '--no-sidebar' # for performances
            ]
        } for p in options.packages }

    for package_name in packages:
        pkg_info = fetch_source(package_name, 
                                versions.get(package_name), 
                                sources)
        package_infos[package_name] = pkg_info

        versions[package_name] = pkg_info['info']['version']

    with (options.build_dir/VERSIONS).open('w') as f:
        json.dump(versions, f)

    # 2. generate docs with pydoctor

    print('[+] generating docs...')
    dist = options.build_dir / WWW
    dist.mkdir(exist_ok=True)
    if options.packages is not None:
        intersphinx_args = []
    else:
        intersphinx_args = list(generate_intersphinx_args(packages))

    _is_verbose = options.packages is not None or options.verbose

    for i, package_name in enumerate(packages):
        
        _pydoctor_exit_code = run_pydoctor(package_name, 
            versions[package_name], 
            sources=sources, 
            dist=dist, 
            args=intersphinx_args + packages[package_name]['pydoctor_args'], 
            verbose=_is_verbose)

        if _build_start_time+_build_timeout < datetime.datetime.now() and i < len(packages)-1:
            print('[!] could not finish building all docs within the required time')
            _exit_code = 21
            break
        
        if _is_verbose and _pydoctor_exit_code!=0:
            _exit_code = 24

    # 3. create latest symlinks, for packages that we actually created docs for.
    for package_name, version in versions.items():
        if package_name not in packages:
            continue
        if not (dist / package_name / version / 'objects.inv').exists():
            if _exit_code!=21:
                print(f'[!] looks like pydoctor build failed for {package_name}-{version}')
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
        options.readme_file.read_text()
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

    return _exit_code
