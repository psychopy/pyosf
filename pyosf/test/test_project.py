# -*- coding: utf-8 -*-
"""
Created on Fri Feb  5 16:01:26 2016

@author: lpzjwp
"""
from __future__ import absolute_import, print_function

from pyosf import remote, project


def test_open_project():
    session = remote.Session(username='jon@peirce.org.uk',
                             password='aTestPassword')
    rem_proj = session.open_project('qgt58')
    proj = project.Project(project_file="tmp/test.proj",
                           root_path="tmp", osf=rem_proj)
    # test the saving of the file
    proj.save()
    # having saved it we can test that it reloads without user/password
    proj = project.Project(project_file="tmp/test.proj")

    print(proj)

if __name__ == "__main__":
    import pytest
    pytest.main(args=[__file__, '-s'])
