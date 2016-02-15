# -*- coding: utf-8 -*-
"""
Created on Fri Feb  5 16:01:26 2016

@author: lpzjwp
"""
from __future__ import absolute_import, print_function

from pyosf import remote, project, constants
import time
import os
from os.path import join
import gc
import shutil
import hashlib


def do_sync(proj):
    changes = proj.get_changes()
    print(changes)
    changes.apply(proj)
    proj.save()


def print_all_changes(changes):
    for change_type in changes._change_types:
        this_dict = getattr(changes, change_type)
        if len(this_dict):
            print("{}:".format(change_type))
            for path in this_dict:
                print(" - {}".format(path))


class TestProjectChanges():

    def teardown(self):
        return
        # take a copy of the remote project files to revert to later
        shutil.rmtree(self.proj_root)
        shutil.copytree(self.safe_copy, self.proj_root)
        # perform a sync with remote to reset all the files there
        proj = project.Project(project_file=self.proj_file)
        do_sync(proj)

    def setup(self):
        self.proj_id = 'qgt58'
        self.this_dir, filename = os.path.split(__file__)
        self.tmp_folder = join(self.this_dir, "tmp")
        self.proj_file = join(self.this_dir, "tmp", "test.proj")
        self.proj_root = join(self.this_dir, "tmp", "files")

        if os.path.isfile(self.proj_file):
            os.remove(self.proj_file)  # start with no project file
        if os.path.isdir(self.proj_root):
            shutil.rmtree(self.proj_root)  # start with no project root

        # first time around we need to supply username/password
        session = remote.Session(username='jon@peirce.org.uk',
                                 password='aTestPassword')  # to get a token
        self.osf_proj = session.open_project(self.proj_id)

        # in future we just give the proj_file and the rest can be recreated
        proj = project.Project(project_file=self.proj_file,
                               root_path=self.proj_root, osf=self.osf_proj)

        # test the saving of the file
        print("Getting initial state of project")
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
        proj.save()

        # having saved it we can test that it reloads without user/password
        print("Re-running get_changes(). Should be None")
        proj = project.Project(project_file=self.proj_file)
        t0 = time.time()
        changes = proj.get_changes()
        t1 = time.time()
        print("\nRedoing - indexing and finding diffs took {:.3f}s"
              .format(t1-t0))
        print(changes)  # prints a prettified table
        print_all_changes(changes)

        # take a copy of the remote project files to revert to later
        self.safe_copy = join(self.tmp_folder, "files_copy")
        if os.path.isdir(self.safe_copy):
            shutil.rmtree(self.safe_copy)
        shutil.copytree(self.proj_root, self.safe_copy)

    def test_save_load_proj(self):

        def namestr(obj, namespace):  # return string of gc.referrers
            return [name for name in namespace if namespace[name] is obj]

        # check that nothing else has created a ref to changes (no circular)
        proj = project.Project(project_file=self.proj_file)
        changes = proj.get_changes()
        assert len(gc.get_referrers(changes)) == 1
        del proj
        if len(gc.get_referrers(changes)) > 0:
            for ref in gc.get_referrers(changes):
                print(namestr(ref, locals()))

    def test_new_to_remote(self):
        # add a folder and some files locally
        print("Creating new files locally")
        orig = join(self.proj_root, 'visual')
        new = join(self.proj_root, 'visual2')
        if os.path.isdir(new):
            shutil.rmtree(new)
        shutil.copytree(orig, new)
        # sync with the new files to test upload and folder creation
        proj = project.Project(project_file=self.proj_file)
        do_sync(proj)
        proj.save()

    def test_conflict(self):
        # create a conflict by changing a file in both locations
        proj = project.Project(project_file=self.proj_file)
        pass  # TODO: fix to use update code (rather than upload)
#        last_index = proj.index
#        # find a text file
#        for asset in last_index:
#            if asset['path'].endswith('text_in_visual.txt'):
#                break
#        path = asset['full_path']
#        # modify it
#        with open(path, 'ab') as f:
#            f.write("A bit of added text. ")
#        # get the new SHA (needed to verify successful upload)
#        with open(path, "rb") as f:
#            hash_func = getattr(hashlib, constants.SHA.lower())
#            asset[constants.SHA] = hash_func(f.read()).hexdigest()
#        proj.osf.add_file(asset)
#        # change again locally
#        with open(path, 'ab') as f:
#            f.write("And some more added text. ")
#        # sync with the new files to test conflict resolution
#        do_sync(proj)


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
