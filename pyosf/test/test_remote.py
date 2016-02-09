# -*- coding: utf-8 -*-
"""
Created on Fri Feb  5 16:01:26 2016

@author: lpzjwp
"""
from __future__ import absolute_import, print_function

from pyosf import remote

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
                    print(" - {}: {}".format(proj['id'], proj['title']))

    def test_search_projects(self):
        projs = self.session.search_project_names('Is it just motion')
        assert len(projs > 0)
        print("Found projects by name : {}".format(projs))

    def test_search_me(self):
        print("Finding projects for 'me' ({})".format(self.session.username))
        userProjects = self.session.find_user_projects()
        for proj in userProjects:
            if printing:
                print(" - {}: {}".format(proj['id'], proj['title']))

    def test_file_listing(self):
        proj_id = 'qgt58'
        print("\n** Finding Files **")
        proj = self.session.open_project(proj_id)
        print(repr(proj), proj.title, "nodes:")
        for this_child in proj.children:
            print(' {} ({}), parent={}'
                  .format(this_child.title, this_child, this_child.parent))

        # look at some file objects for proj
        print(repr(proj), proj.title, "files:")
        file_list = proj.create_index()
        for n, this_file in enumerate(file_list):
            if n > 5:
                print('...')
                break
            print(' - ', this_file['name'], this_file['kind'],
                  this_file['size'], this_file['path'])
            print("  links:", this_file['links'])

if __name__ == "__main__":
    import pytest
    pytest.main(args=[__file__, '-s'])
