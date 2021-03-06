# -*- coding: utf-8 -*-
"""
Part of the pyosf package
https://github.com/psychopy/pyosf/

Released under MIT license

@author: Jon Peirce
"""

from __future__ import absolute_import, print_function
from pyosf import remote
import time

printing = True


class TestSession(object):

    def setup_class(self):
        self.session = remote.Session(username='jon@peirce.org.uk',
                                      password='aTestPassword')
        self.user_id = self.session.user_id

    def test_search_user(self, name='peirce'):
        session = self.session
        if printing:
            print("\n** Finding Jon **")
        users = session.find_users(name)
        for user in users:
            full_name = user['full_name']
            user_id = user['id']
            if printing:
                print("Found OSF user {} with id={}"
                      .format(full_name, user_id))
                print("Projects:")
            userProjects = self.session.find_user_projects(user_id)
            for proj in userProjects:
                if printing:
                    print(" - {}: {}".format(proj.id, proj.title))

    def test_search_projects(self):
        projs = self.session.find_projects('Is it just motion',
                                           tags='PsychoPy')
        print("Found projects by name : ")
        for proj in projs:
            print(" - {}".format(proj.title))

    def test_session_token(self):
        # this is a @property def so make sure the code runs
        print(self.session.token)

    def test_file_attributes(self):
        proj = self.session.open_project('nqwss')
        # includes several @property attributes that should be tested
        this_id = proj._node_file_list()[0]['id']
        node = remote.FileNode(self.session, this_id)
        print("Testing attribs for {}:".format(node.name))
        for attr_name in dir(node):
            print(" - {} = {}".format(attr_name, getattr(node, attr_name)))

    def test_search_me(self):
        print("Finding projects for 'me' ({})".format(self.session.username))
        userProjects = self.session.find_user_projects()
        for proj in userProjects:
            if printing:
                print(" - {}: {}".format(proj.id, proj.title))

    def test_file_listing(self):
        # will use a public project with child nodes
        proj_id = 'https://api.osf.io/v2/nodes/nqwss'  # Jons silencing project
        print("\n** Finding Files **")
        proj = self.session.open_project(proj_id)  # testing request by https
        print(repr(proj), proj.title, "nodes:")
        for this_child in proj.children:
            print(' {} ({}), parent={}'
                  .format(this_child.title, this_child, this_child.parent))
        for attr_name in dir(this_child):
            attr = getattr(this_child, attr_name)
            print("{}.{} = {}".format(this_child.title, attr_name, attr))

        # look at some file objects for proj
        print(repr(proj), proj.title, "files:")
        file_list = proj.create_index()
        for n, this_file in enumerate(file_list):
            if n > 5:
                print('...')
                break
            if this_file['kind'] == 'file':
                size = "{}bytes".format(this_file['size'])
            else:
                size = ""
            print(' - {} ({},)'.format(this_file['path'],
                                       this_file['kind'], size))

    def test_create_delete_proj(self):
        nProjects = len(self.session.find_user_projects())
        longPara = """Testing that the description works, with unicode chars:
        ‰ Ä ™
        """
        proj = self.session.create_project(title="A test project with tags",
                                           descr=longPara,
                                           tags=['programming', 'test'])
        nProjectsNow = len(self.session.find_user_projects())
        time.sleep(0.5)
        assert nProjectsNow == nProjects+1
        time.sleep(5.0)  # don't delete before everything calms down
        self.session.delete_project(proj.id)
        time.sleep(5.0)
        nProjectsNow = len(self.session.find_user_projects())
        assert nProjectsNow == nProjects

if __name__ == "__main__":
    import pytest
    pytest.main(args=[__file__, '-s'])
