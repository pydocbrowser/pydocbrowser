"""
We delete all the files in directories that are not the latest version 
to try to reduce the size of the website because Github Pages only allows 1Gb.
"""
from pathlib import Path
import shutil
import os

if __name__ == '__main__':

    WWW = Path(__file__).parent / 'build' / 'www'

    for entry in WWW.iterdir():
        # Not a docs folder
        if not entry.is_dir():
            continue
        # A new latest symlink, we leave it untouched
        # because this script relies on the fact that github
        # turn symlinks into actual folders, we must run it only
        # on older generated docs
        latest = (entry / 'latest')
        assert latest.exists()

        if latest.is_symlink():
            continue

        assert latest.is_dir()
        # Deletes everything except latest directory
        for subfolder in entry.iterdir():
            if not subfolder.is_dir():
                continue
            if subfolder.name == 'latest':
                continue
            remove = subfolder.as_posix()
            print(f'Removing files in {remove!r} (except objects.inv)')
            for _f in subfolder.iterdir():
                if _f.is_dir():
                    shutil.rmtree(_f.as_posix())
                elif _f.name != 'objects.inv':
                    os.remove(_f.as_posix())
