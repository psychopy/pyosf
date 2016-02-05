"""The main classes to be used by external scripts/apps

These should be imported into the root project __init__.

Standard usage will then be::

    import pyosf
    #create an authenticated session
    session = pyosf.session(username='something', token=someValue)
    proj_ids = session.find_project_ids(searchStr = 'stroop')
    proj = proj_ids
"""

import os
try:
    from psychopy import logging
except:
    import logging
from . import remote
import json

class Project(object):
    """Stores the project information (the remote proejct on OSF, information
    about the local files, and a record of the previous index of files)
    """
    def __init__(self, project_path=None, root_path=None, session=None):
        """If project file has already been created then this can be used
        to detect the root_path and create a remote.Session but otherwise a
        Session object and root_path should be provided.
        """
        self.project_path = project_path
        self.root_path = root_path
        self.session = session # not needed if project_path exists
        # these will be created from project_path or from root_path
        self.index = None # the most recent index of files
        self.local = None # a local.LocalFiles object (to be indexed)

    def __repr__(self):
        return "Project(%r)" %(self.id)

    def save(self, proj_path=None):
        """Save the project to a json-format file
        """
        if proj_path is None:
            proj_path = self.project_path
        if not os.path.isdir(os.path.dirname(proj_path)):
            os.mkdirs(os.path.dirname(proj_path))
        if not os.path.isfile(proj_path):
            logging.info("Creating new Project file: {}".format(proj_path))
        # create the fields to save
        d = {}
        d['root_path'] = self.root_path
        d['session'] = self.session.toDict()
        d['index'] = self.index
        # do the actual file save
        with open(projPath, 'wb') as f:
            json.dump(self.tree, f, indent=4)

    def load(self, proj_path=None):
        """Load the project from a json-format file
        """
        if projPath is None:
            projPath = self.project_path
        if not os.path.isfile(proj_path):
            self.session = remote.Session()

        # todo: handle the case that the path doesn't (yet) exist
        with open(projPath, 'r') as f:
            d = json.load(f)
        if not self.root_path:
            self.root_path = d['root_path']
        elif self.root_path != d['root_path']:
            logging.warn("The Project was given a directory that does not "
                         "match the previous stored location. "
                         "Using new location.")
        self.session = remote.Session(token=d['session']['token'])
        self.index = d['index']

    def sync(self):
        pass
        # todo

if __name__ == "__main__":
    session = remote.Session()
    proj = Project(proj_path="~/.psychopy/projects/test.proj")
