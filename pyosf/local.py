
from __future__ import absolute_import, print_function
import os
from datetime import datetime
import json
import hashlib
from . import constants


class LocalFiles(object):
    def __init__(self, root_path):
        # these should be reset when the path is set
        self.nFiles = 0
        self.nFolders = 0
        self.sha_list = []
        # this should trigger the work to be done
        self.root_path = root_path

    def create_index(self, path=None):
        """Scans the tree of nodes recursively and returns
        file/folder details as a flat list of dicts
        """
        if path is None:
            path = self.root_path
        if os.path.isdir(path):
            if path is not self.root_path:  # don't store root as a folder
                d = {}
                d['kind'] = "directory"
                d['full_path'] = path
                d['path'] = os.path.relpath(path, self.root_path)
                files = [d]
                self.nFolders += 1
            else:
                files = []
            # then find children as well
            [files.extend(self.create_index(os.path.join(path, x)))
                for x in os.listdir(path)]
            return files
        else:
            d = {}
            d['full_path'] = path
            d['path'] = os.path.relpath(path, self.root_path)
            d['kind'] = "file"
            with open(path, "rb") as f:
                hash_func = getattr(hashlib, constants.SHA.lower())
                d[constants.SHA] = hash_func(f.read()).hexdigest()
            d['date_modified'] = datetime.fromtimestamp(os.path.getmtime(path)
                                                        ).isoformat()
            self.nFiles += 1
            return [d]

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
        self.index = self.create_index()

    def save(self, filename):
        """Save the tree of this path to a json file
        """
        with open(filename, 'wb') as f:
            json.dump(self.index, f, indent=4)
