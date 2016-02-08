# -*- coding: utf-8 -*-
"""
Created on Fri Feb  5 16:01:26 2016

@author: lpzjwp
"""
from __future__ import absolute_import, print_function

from pyosf import remote, project
import time
import os

this_dir, filename = os.path.split(__file__)
proj_file = os.path.join(this_dir, "tmp", "test.proj")
proj_root = os.path.join(this_dir, "tmp", "files")
print(proj_root)


def test_open_project():
    session = remote.Session(username='jon@peirce.org.uk',
                             password='aTestPassword')
    rem_proj = session.open_project('qgt58')
    proj = project.Project(project_file=proj_file,
                           root_path=proj_root, osf=rem_proj)
    # test the saving of the file
    t0 = time.time()
    changes = proj.get_changes()
    t1 = time.time()
    print("Indexing and finding diffs took {:.3f}s".format(t1-t0))
    print(changes)
    print("Add local:")
    for f in changes.add_local.keys():
        print(" - {}".format(f))
    print("Add remote:")
    for f in changes.add_remote.keys():
        print(" - {}".format(f))
    changes.apply()
    proj.save()
    # having saved it we can test that it reloads without user/password
    proj = project.Project(project_file=proj_file)


if __name__ == "__main__":
    import pytest
    pytest.main(args=[__file__, '-s'])
