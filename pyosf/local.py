# -*- coding: utf-8 -*-
"""Class to track local files

Part of the pyosf package
https://github.com/psychopy/pyosf/

Released under MIT license

Created on Sun Feb  7 21:31:15 2016

@author: lpzjwp
"""

from __future__ import absolute_import, print_function
import os
from datetime import datetime
import json
import hashlib
from . import constants

try:
    from psychopy import logging
except ImportError:
    import logging


class LocalFiles(object):
    def __init__(self, root_path):
        # these should be reset when the path is set
        self.nFiles = 0
        self.nFolders = 0
        self.sha_list = []
        # this should trigger the work to be done
        self.root_path = root_path
        self._index = None
        self._needs_rebuild_index = False

    def rebuild_index(self):
        logging.info("Indexing LocalFiles")
        self._index = self._create_index()
        self._needs_rebuild_index = False

    def _create_index(self, path=None):
        """Scans the tree of nodes recursively and returns
        file/folder details as a flat list of dicts
        """
        if path is None:
            path = self.root_path
        d = {}
        d['full_path'] = path
        d['path'] = os.path.relpath(path, self.root_path)
        d['date_modified'] = datetime.fromtimestamp(os.path.getmtime(path)
                                                    ).isoformat()
        if os.path.isdir(path):
            if path is not self.root_path:  # don't store root as a folder
                d['kind'] = "folder"
                files = [d]
                self.nFolders += 1
            else:
                files = []
            # then find children as well
            [files.extend(self._create_index(os.path.join(path, x)))
                for x in os.listdir(path)]
            return files
        else:
            d['kind'] = "file"
            try:
                d['size'] = os.path.getsize(path)
            except:
                d['size'] = 0
            with open(path, "rb") as f:
                hash_func = getattr(hashlib, constants.SHA.lower())
                d[constants.SHA] = hash_func(f.read()).hexdigest()
            self.nFiles += 1
            return [d]

    @property
    def index(self):
        if self._index is None or self._needs_rebuild_index:
            self.rebuild_index()
        return self._index

    @property
    def root_path(self):
        return self._root_path

    @root_path.setter
    def root_path(self, root_path):
        self._root_path = root_path
        # create if it doesn't exist yet
        if not os.path.isdir(self._root_path):
            os.makedirs(self._root_path)
        # reset counters
        self._nFiles = 0
        self._nFolders = 0
        self.md5_list = []

    def save(self, filename):
        """Save the tree of this path to a json file
        """
        with open(filename, 'wb') as f:
            json.dump(self.index, f, indent=2)
