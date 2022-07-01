"""
We delete all the files in directories that are not the latest version 
to try to reduce the size of the website because Github Pages only allows 1Gb.
"""
from pathlib import Path
import shutil

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
            if subfolder.name == 'latest':
                continue
            remove = subfolder.as_posix()
            print(f'Removing {remove!r}')
            shutil.rmtree(remove)
