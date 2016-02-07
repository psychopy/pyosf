from __future__ import print_function
import os
import sys
from datetime import datetime
import json
import hashlib


class LocalFiles(object):
    def __init__(self, root_path):
        # these should be reset when the path is set
        self.nFiles = 0
        self.nFolders = 0
        self.md5_list = []
        # this should trigger the work to be done
        self.root_path = root_path

    def create_index(self, path=None):
        """Scans the tree of nodes recursively and returns
        file/folder details as a flat list of dicts
        """
        if path is None:
            path = self.root_path
        if os.path.isdir(path):
            d = {}
            d['kind'] = "directory"
            d['path'] = path
            files = [d]
            self.nFolders += 1
            # then find children as well
            [files.extend(self.create_index(os.path.join(path, x)))
                for x in os.listdir(path)]
            return files
        else:
            d = {}
            d['path'] = path
            d['kind'] = "file"
            d['md5'] = hashlib.md5(path).hexdigest()
            d['date_modified'] = datetime.fromtimestamp(os.path.getmtime(path)
                                                        ).isoformat()
            self.nFiles += 1
            return [d]

    def _create_tree(self, path=None):
        """Examines the current node recursively and returns a dict tree
        """
        if path is None:
            path = self.path
        d = {'name': os.path.basename(path),
             'path': path}
        if os.path.isdir(path):
            d['kind'] = "directory"
            d['children'] = [self._scan_path_recursive(os.path.join(path, x))
                             for x in os.listdir(path)]
            self.nFolders += 1
        else:
            d['kind'] = "file"
            d['md5'] = hashlib.md5(path).hexdigest()
            d['date_modified'] = os.path.getmtime(path)
            d['size'] = os.path.getsize(path)
            self.nFiles += 1
        return d

    @property
    def root_path(self):
        return self._root_path

    @root_path.setter
    def root_path(self, root_path):
        self._root_path = root_path
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

if __name__ == "__main__":
    import time
    t0 = time.time()
    if sys.platform == 'darwin':
        root_path = '/Users/lpzjwp/Dropbox'
    elif sys.platform.startswith('linux'):
        root_path = '/home/lpzjwp/Dropbox'
    localDB = LocalFiles(root_path)
    t1 = time.time()
    localDB.save('tmp.json')
    t2 = time.time()
    print(t1-t0, t2-t1)
    print("nFolders={}, nFiles={}".format(localDB.nFolders, localDB.nFiles))
    print("took {}s to scan and {}s to write as json".format(t1-t0, t2-t1))
