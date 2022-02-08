#!/usr/bin/env python3
import configparser
import io
import json
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
import posixpath
from typing import Dict, List

import jinja2
import mistletoe
import pkg_resources
import pydoctor.driver
from pydoctor import model
from sphinx.util.typing import Inventory
from sphinx.util.inventory import InventoryFile
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


def is_documented_in_inventory(ob: model.Documentable, inventory: Inventory) -> bool:
    if isinstance(ob, model.Module):
        return ob.fullName() in inventory['py:module']
    if isinstance(ob, model.Class):
        return (
            ob.fullName() in inventory['py:class']
            or ob.fullName() in inventory['py:exception']
        )
    if ob.kind == model.DocumentableKind.FUNCTION:
        return ob.fullName() in inventory['py:function']
    if ob.kind == model.DocumentableKind.METHOD:
        return ob.fullName() in inventory['py:method']
    if ob.kind in (
        model.DocumentableKind.CLASS_VARIABLE,
        model.DocumentableKind.INSTANCE_VARIABLE,
    ):
        return ob.fullName() in inventory['py:attribute']
    if ob.kind == model.DocumentableKind.PROPERTY:
        return ob.fullName() in inventory.get('py:property', ())
    # TODO: it's not ideal that we default to True, ideally we could cover all kinds
    return True


def inventory_members(inventory: Inventory):
    for x in inventory['py:class']:
        yield x
    for x in inventory['py:exception']:
        yield x
    for x in inventory['py:function']:
        yield x
    for x in inventory['py:method']:
        yield x
    for x in inventory['py:attribute']:
        yield x
    for x in inventory['py:property']:
        yield x


class SphinxAwareSystem(model.System):
    def __init__(self, inventory: Inventory) -> None:
        super().__init__()
        self._inventory = inventory
        self._public_modules = set(inventory['py:module'])
        for x in inventory_members(inventory):
            self._public_modules.add(x.rsplit('.', maxsplit=1)[0])

    def privacyClass(self, ob: model.Documentable):
        if isinstance(ob, model.Module):
            if ob.fullName() in self._public_modules:
                return model.PrivacyClass.VISIBLE

        if not is_documented_in_inventory(ob, self._inventory):
            # TODO: if ob is return type by another public API member consider it public
            return model.PrivacyClass.PRIVATE

        return super().privacyClass(ob)

class InventoryLookupError(Exception):
    pass

def system_for_sphinx_inventory(inventory_url: str):
    inventory_url = packages[package_name]['sphinx_inventory_url']
    url_base = inventory_url.rsplit('/', maxsplit=1)[0]
    inventory_path = inventories / (package_name + '.inv')
    try:
        with inventory_path.open('rb') as f:
            inventory = InventoryFile.load(f, url_base, posixpath.join)
    except FileNotFoundError:
        resp = requests.get(inventory_url, stream=True)
        if resp.status_code != 200:
            raise InventoryLookupError(f'sphinx_inventory_url returned unexpected http status code {resp.status_code}')
        inventory_bytes = resp.content
        inventory = InventoryFile.load(
            io.BytesIO(inventory_bytes), url_base, posixpath.join
        )
        with inventory_path.open('wb') as f:
            f.write(inventory_bytes)

    if 'py:module' not in inventory:
        raise InventoryLookupError(f"sphinx inventory does not contain py:module")

    system = SphinxAwareSystem(inventory)
    system.options.docformat = docformat
    return system


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

    package_infos = {}

    with open('packages.toml') as f:
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

    with open('versions.json', 'w') as f:
        json.dump(versions, f)

    shutil.rmtree(download_dir)

    # 2. generate docs with pydoctor

    dist = Path('dist')
    dist.mkdir(exist_ok=True)

    inventories = Path('inventories')
    inventories.mkdir(exist_ok=True)

    for path in sources.iterdir():
        sourceid = path.name
        package_name, version = sourceid.rsplit('-', maxsplit=1)

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

        print('generating', sourceid)

        system = None

        if 'sphinx_inventory_url' in packages[package_name]:
            try:
                system = system_for_sphinx_inventory(
                    packages[package_name]['sphinx_inventory_url']
                )
            except InventoryLookupError as e:
                print(f'[warning] skipping {package_name} because sphinx inventory lookup failed: {e}')
                continue

        out_dir.mkdir(parents=True)

        pydoctor.driver.main(
            # fmt: off
            [
                str(package_paths[0]),
                '--html-output', out_dir,
                '--docformat', docformat,
            ],
            # fmt: on
            system=system,
        )

    # 3. create latest symlinks
    for package_name, version in versions.items():
        if not (dist / package_name).exists():
            continue

        latest = dist / package_name / 'latest'
        latest.unlink(missing_ok=True)
        latest.symlink_to(version)

    # 4. create start page
    env = jinja2.Environment(loader=jinja2.PackageLoader("pydoc"), autoescape=True)

    readme_html = mistletoe.markdown(
        pkg_resources.resource_string(__name__, 'README.md').decode()
    )
    contributing_html = mistletoe.markdown(
        pkg_resources.resource_string(__name__, 'CONTRIBUTING.md').decode()
    )

    with open(dist / 'index.html', 'w') as f:
        f.write(
            env.get_template('index.html').render(
                readme=readme_html,
                contributing=contributing_html,
                packages=package_infos.items(),
            )
        )
