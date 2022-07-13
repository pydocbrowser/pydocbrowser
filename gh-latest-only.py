"""
We delete all the files in directories that are not the latest version 
to reduce the size of the website because Github Pages only allows 1Gb.
"""
from pathlib import Path
import shutil
import os
from typing import Tuple

def get_version(s:str) -> Tuple[int, int, int]:
    parts = s.strip().split('.')
    intparts = []
    
    for p in parts:
        try:
            v = int(p)
        except:
            v = 0
        intparts.append(v)
    
    for _ in range(3-len(intparts)):
        intparts.append(0)
    
    assert len(intparts)==3
    return tuple(intparts)

if __name__ == '__main__':

    WWW = Path(__file__).parent / 'build' / 'www'

    for entry in WWW.iterdir():
        # Not a docs folder
        if not entry.is_dir():
            continue
        
        # Determine the folders to delete...

        names = [_e.name for _e in entry.iterdir() if _e.name!='latest']
        versions = {get_version(_v):_v for _v in names}
        latest_version = max(versions.keys())
        latest_version_name = versions[latest_version]

        names_to_delete = [_n for _n in names if _n != latest_version_name]

        # Sanity checks...
        latest = (entry / 'latest')
        assert latest.exists()
        
        # Deletes everything except latest directory
        for subfolder_name in names_to_delete:
            subfolder = entry / subfolder_name
            if not subfolder.is_dir():
                print(f'not a directory: {subfolder}')
                continue
            if subfolder.name == 'latest':
                print(f'latest directory: {subfolder}')
                continue
            remove = subfolder.as_posix()
            
            # skips already removed entries
            if len(list(subfolder.iterdir()))==1 and \
               (subfolder/'objects.inv').exists():
                continue
            
            print(f'Removing files in {remove!r} (except objects.inv)')
            for _f in subfolder.iterdir():
                if _f.is_dir():
                    shutil.rmtree(_f.as_posix())
                elif _f.name != 'objects.inv':
                    os.remove(_f.as_posix())
