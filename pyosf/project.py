# -*- coding: utf-8 -*-
"""The main classes needed by external scripts

The Project class tracks a `remote.Project()` and `local.LocalFiles` objects
and compares them using `sync.Changes()`

Part of the pyosf package
https://github.com/psychopy/pyosf/

Released under MIT license

Created on Sun Feb  7 21:31:15 2016

@author: lpzjwp
"""

from __future__ import absolute_import, print_function
import os
import sys
import requests
try:
    from psychopy import logging
except:
    import logging
from . import remote, local, sync
import json

PY3 = sys.version_info > (3,)


class Project(object):
    """Stores the project information for synchronization.

    Stores the id and username for the remote.Project on OSF, the location of
    the local files, and a record of the index at the point of previous sync

    Parameters
    ----------

    project_file : str
        Location of the project file with info

    root_path : str
        The root of the folder where the local files are situated

    osf : pyosf.remote.OSFProject instance)
        The remote project that will be synchronised.

    """
    def __init__(self, project_file=None, root_path=None, osf=None,
                 name='', autosave=True):
        self.autosave = autosave  # try to save file automatically on __del__
        self.project_file = project_file
        self.root_path = root_path  # overwrite previous (indexed) location
        self.name = name  # not needed but allows storing a short descr name
        # these will be update from project file loading if it exists
        self.index = []
        self.username = None
        self.project_id = None
        self.connected = False  # have we gone online yet?
        # load the project file (if exists) for info about previous sync
        if project_file:
            self.load(project_file)

        # check/set root_path
        if self.root_path is None:
            self.root_path = root_path  # use what we just loaded
        elif root_path not in [None, self.root_path]:
            logging.warn("The requested root_path and the previous root_path "
                         "differ. Using the requested path."
                         "given: {}"
                         "stored: {}".format(root_path, self.root_path))
        if self.root_path is None:
            logging.warn("Project file failed to load a root_path "
                         "for the local files and none was provided")

        self.osf = osf  # the self.osf is as property set on-access

    def __repr__(self):
        return "Project({})".format(self.project_file)

    def __del__(self):
        if self.autosave:
            self.save()

    def save(self, proj_path=None):
        """Save the project to a json-format file

        The info will be:
            - the `username` (so `remote.Project` can fetch an auth token)
            - the project id
            - the `root_path`
            - the current files `index`
            - a optional short `name` for the project

        Parameters
        ----------

        proj_path : str
            Not needed unless saving to a new location.

        """
        if proj_path is None:
            proj_path = self.project_file
        if not os.path.isdir(os.path.dirname(proj_path)):
            os.makedirs(os.path.dirname(proj_path))
        if not os.path.isfile(proj_path):
            logging.info("Creating new Project file: {}".format(proj_path))
        # create the fields to save
        d = {}
        d['root_path'] = self.root_path
        d['name'] = self.name
        d['username'] = self.username
        d['project_id'] = self.project_id
        d['index'] = self.index
        # do the actual file save
        with open(proj_path, 'wb') as f:
            json_str = json.dumps(d, indent=2)
            if PY3:
                f.write(bytes(json_str, 'UTF-8'))
            else:
                f.write(json_str)
        logging.info("Saved proj file: {}".format(proj_path))

    def load(self, proj_path=None):
        """Load the project from a json-format file

        The info will be:
            - the `username` (so `remote.Project` can fetch an auth token)
            - the project id the `root_path`
            - the current files `index`
            - a optional short `name` for the project

        Parameters
        ----------

        proj_path : str
            Not needed unless saving to a new location.

        Returns
        ----------

        tuple (last_index, username, project_id, root_path)

        """
        if proj_path is None:
            proj_path = self.project_file
        if proj_path is None:  # STILL None: need to set later
            return
        elif not os.path.isfile(os.path.abspath(proj_path)):  # path not found
            logging.warn('No proj file: {}'.format(os.path.abspath(proj_path)))
        else:
            with open(os.path.abspath(proj_path), 'r') as f:
                d = json.load(f)
            self.username = d['username']
            self.index = d['index']
            self.project_id = d['project_id']
            self.root_path = d['root_path']
            if 'name' in d:
                self.name = d['name']
            else:
                self.name = ''
            logging.info('Loaded proj: {}'.format(os.path.abspath(proj_path)))

    def get_changes(self):
        """Return the changes to be applied
        """
        changes = sync.Changes(proj=self)
        self.connected = True  # we had to go online to get changes
        return changes

    @property
    def osf(self):
        """Get/sets the osf attribute. When
        """
        if self._osf is None:
            self.osf = self.project_id  # go to setter using project_id
        # if one of the above worked then self._osf should exist by now
        return self._osf

    @osf.setter
    def osf(self, project):
        if isinstance(project, remote.OSFProject):
            self._osf = project
            self.username = self._osf.session.username
            self.project_id = self._osf.id
        elif self.username is None:  # if no project then we need username
            raise AttributeError("No osf project was provided but also "
                                 "no username or authentication token: {}"
                                 .format(project))
        else:  # with username create session and then project
            try:
                session = remote.Session(self.username)
            except requests.exceptions.ConnectionError:
                self._osf = None
                self.connected = False
                return
            if self.project_id is None:
                raise AttributeError("No project id was available. "
                                     "Project needs OSFProject or a "
                                     "previous project_file"
                                     .format(project))
            else:
                self._osf = remote.OSFProject(session=session,
                                              id=self.project_id)
                self.connected = True

    @property
    def root_path(self):
        return self.__dict__['root_path']

    @root_path.setter
    def root_path(self, root_path):
        self.__dict__['root_path'] = root_path
        if root_path is None:
            self.local = None
        else:
            self.local = local.LocalFiles(root_path)
