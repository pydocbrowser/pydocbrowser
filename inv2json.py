#!/usr/bin/env python3
import json
import posixpath
import sys

from sphinx.util.inventory import InventoryFile

with open(sys.argv[1], 'rb') as f:
    inv = InventoryFile.load(f, '', posixpath.join)

print(json.dumps(inv))
