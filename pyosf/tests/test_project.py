# -*- coding: utf-8 -*-
"""
Created on Fri Feb  5 16:01:26 2016

@author: lpzjwp
"""
from __future__ import absolute_import, print_function

from pyosf import remote, project
import time
import os
from os.path import join
import gc
import shutil

this_dir, filename = os.path.split(__file__)
tmp_folder = join(this_dir, "tmp")
proj_file = join(this_dir, "tmp", "test.proj")
proj_root = join(this_dir, "tmp", "files")

#if os.path.isfile(proj_file):
#    os.remove(proj_file)  # start with no project file (test creation)

#if os.path.isdir(proj_root):
#    shutil.rmtree(proj_root)  # start with no project file (test creation)


def print_all_changes(changes):
    for change_type in changes._change_types:
        this_dict = getattr(changes, change_type)
        if len(this_dict):
            print("{}:".format(change_type))
            for path in this_dict:
                print(" - {}".format(path))


def test_open_project():
    # first time around we need to supply username/password
    session = remote.Session(username='jon@peirce.org.uk',
                             password='aTestPassword')  # to get an auth token
    osf_proj = session.open_project('qgt58')
    # in future we just give the proj_file and the rest can be recreated
    proj = project.Project(project_file=proj_file,
                           root_path=proj_root, osf=osf_proj)
    # test the saving of the file
    t0 = time.time()
    changes = proj.get_changes()
    t1 = time.time()
    print("Indexing and finding diffs took {:.3f}s".format(t1-t0))
    print(changes)  # prints a prettified table
    t2 = time.time()
    print("Applying changes")
    changes.apply(proj)
    t3 = time.time()
    print("Applying changes took {:.3f}s".format(t3-t2))
    # check that nothing else has created a ref to changes (no circular)
    assert len(gc.get_referrers(changes)) == 1

    del proj
    # proj.save()  # should be saved automatically when proj is gc-ed

    # having saved it we can test that it reloads without user/password
    proj = project.Project(project_file=proj_file)
    t0 = time.time()
    changes = proj.get_changes()
    t1 = time.time()
    print("\nRedoing - indexing and finding diffs took {:.3f}s".format(t1-t0))
    print(changes)  # prints a prettified table
    print_all_changes(changes)

    #take a copy of the remote project files to revert to later
    safe_copy = join(tmp_folder, "files_copy")
    if os.path.isdir(safe_copy):
        shutil.rmtree(safe_copy)
    shutil.copytree(proj_root, safe_copy)

    # add a folder and some files locally
    orig = join(proj_root, 'visual')
    new = join(proj_root, 'visual2')
    shutil.rmtree(new)
    shutil.copytree(orig, new)
    # sync with the new files to test upload and folder creation
    changes = proj.get_changes()
    print(changes)
    changes.apply(proj)

    # take a copy of the remote project files to revert to later
    shutil.rmtree(proj_root)
    shutil.copytree(safe_copy, proj_root)
    # perform a sync with remote to reset all the files there
    changes = proj.get_changes()
    changes.apply(proj)
    print(changes)
    proj.save()

if __name__ == "__main__":
    try:
        from psychopy import logging
        console = logging.console
    except ImportError:
        import logging
        console = logging.getLogger()
    console.setLevel(logging.INFO)
    import pytest
    pytest.main(args=[__file__, '-s'])
