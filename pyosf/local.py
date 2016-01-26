import os
import json
import hashlib

class LocalFiles(object):
    def __init__(self, path):
        # these should be reset when the path is set
        self.nFiles = 0
        self.nFolders = 0
        self.sha_list = []
        self._tree = None
        # this should trigger the work to be done
        self.path = path
    def _scan_path_recursive(self, path=None):
        """Examines the current node (folder) 
        """
        if path is None:
            path = self.path
        d = {'name': os.path.basename(path),
            'path': path}
        if os.path.isdir(path):
            d['type'] = "directory"
            d['children'] = [self._scan_path_recursive(os.path.join(path,x)) \
                for x in os.listdir(path)]
            self.nFolders += 1
        else:   
            d['type'] = "file"
            d['sha'] = hashlib.sha256(path).hexdigest()
            d['modified'] = os.path.getmtime(path)
            self.nFiles += 1
        return d
    @property
    def path(self):
        return self._path
    @path.setter
    def path(self, path):
        self._path = path
        #reset counters
        self._nFiles = 0
        self._nFolders = 0
        self.sha_list = []
        #analyse path
        self._tree = self._scan_path_recursive(path)
    def toFile(self, filename):
        """Save the tree of this path to a json file
        """
        with open(filename, 'wb') as f:
            json.dump(self.tree, f, indent=4)
    @property
    def tree(self):
        """Returns the tree of folders/files for this path
        """
        return self._tree

if __name__ == "__main__":
    import time
    t0 = time.time()
    localDB = LocalFiles('/Users/lpzjwp/Dropbox')
    t1 = time.time()
    localDB.toFile('test.json')
    t2 = time.time()
    print t1-t0, t2-t1
    print("nFolders={}, nFiles={}".format(localDB.nFolders, localDB.nFiles))
    print("took {}s to scan and {}s to print as json".format(t1-t0, t2-t1))
