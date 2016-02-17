# -*- coding: utf-8 -*-
"""
Part of the pyosf package
https://github.com/psychopy/pyosf/

Released under MIT license

@author: Jon Peirce
"""

from __future__ import absolute_import, print_function
from pyosf import remote, project, constants, tools
import time
import os
from os.path import join
import gc
import shutil
import copy


def do_sync(proj, print_all=False):
    changes = proj.get_changes()
    print(changes)
    if print_all:
        print_all_changes(changes)
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

    def setup(self):
        # this is done individually for every test
        self.proj = project.Project(project_file=self.proj_file)

    def teardown(self):
        if self.proj is not None:
            self.proj.osf.rebuild_index()
            print("Project state:")
            for asset in self.proj.index:
                print(" - {}".format(asset['path']))
        self.proj = None

    def teardown_class(self):
        self.proj = None
        # take a copy of the remote project for reference
        if os.path.isdir('EndOfLastTest'):
            shutil.rmtree('EndOfLastTest')  # start with no project root
        shutil.copytree(self.proj_root, 'EndOfLastTest')
        # revert the local project to original state
        if os.path.isdir(self.proj_root):
            shutil.rmtree(self.proj_root)  # start with no project root
        shutil.copytree(self.files_orig, self.proj_root)
        # perform a sync with remote to reset all the files there
        proj = project.Project(project_file=self.proj_file)
        do_sync(proj)

    def setup_class(self):
        self.proj_id = 'qgt58'
        self.this_dir, filename = os.path.split(__file__)
        self.files_orig = join(self.this_dir, "files_orig")
        self.tmp_folder = join(self.this_dir, "tmp")
        self.proj_file = join(self.this_dir, "tmp", "test.proj")
        self.proj_root = join(self.this_dir, "tmp", "files")

        if os.path.isfile(self.proj_file):
            os.remove(self.proj_file)  # start with no project file
        if os.path.isdir(self.proj_root):
            shutil.rmtree(self.proj_root)  # start with no project root
        # start with what we know
        shutil.copytree(self.files_orig, self.proj_root)

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
        print_all_changes(changes)
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

    def test_save_load_proj(self):

        def namestr(obj, namespace):  # return string of gc.referrers
            return [name for name in namespace if namespace[name] is obj]

        # check that nothing else has created a ref to changes (no circular)
        changes = self.proj.get_changes()
        assert len(gc.get_referrers(changes)) == 1  # just one ref (ours!)

    def test_add_and_remove_local(self):
        # add a folder and some files locally to propogate to remote
        print("Creating new files locally")
        orig = join(self.proj_root, 'visual')
        new = join(self.proj_root, 'visual2')
        if os.path.isdir(new):
            shutil.rmtree(new)
        shutil.copytree(orig, new)
        # sync with the new files to test upload and folder creation
        do_sync(self.proj)
        self.proj.save()
        print("Removing files locally")
        # then remove the folder and do the sync again
        shutil.rmtree(new)
        do_sync(self.proj)
        self.proj.save()

    def test_add_and_remove_remote(self):
        test_path = 'newFolder/testTextFile.txt'
        # add a folder and file remotely to propogate to local
        # take an arbitrary file from local give a new path and push to remote
        asset = tools.find_by_key(self.proj.local.index, 'path', 'README.txt')
        new_asset = copy.copy(asset)
        # change 'path' for upload but 'full_path' points to orig
        new_asset['path'] = test_path
        self.proj.osf.add_file(new_asset)
        self.proj = None  # discard and recreate

        # now create proj and do sync
        self.proj = project.Project(project_file=self.proj_file)
        do_sync(self.proj)
        self.proj.save()

        print("Removing a file and folder remotely")
        # remove folder and file remotely and propogate to local
        asset = tools.find_by_key(self.proj.osf.index, 'path', test_path)
        self.proj.osf.del_file(asset)
        container, name = os.path.split(test_path)
        asset = tools.find_by_key(self.proj.osf.index, 'path', container)
        self.proj.osf.del_file(asset)

    def test_conflict(self):
        fname = 'text_in_visual.txt'
        # make changes to both and test sync
        self._make_changes(self.proj, fname,
                           local_change=True, remote_change=True)
        print("Doing conflicted sync")
        do_sync(self.proj)

    def test_local_updated(self):
        fname = 'lowerLevel.txt'
        # make changes to both and test sync
        self._make_changes(self.proj, fname,
                           local_change=True, remote_change=False)
        print("Sync with a local update")
        do_sync(self.proj)

    def test_remote_updated(self):
        fname = 'README.txt'
        # make changes to both and test sync
        self._make_changes(self.proj, fname,
                           local_change=False, remote_change=True)
        print("Sync with a remote update")
        do_sync(self.proj)

    def test_folder_in_folder(self):
        folder_path = "folderLevel1/folderLevel2"
        self.proj.osf.add_container(folder_path, kind='folder')
        print("Test sync with a folder in folder")
        do_sync(self.proj)
        assert os.path.isdir(join(self.proj_root, folder_path))

    def _make_changes(self, proj, filename,
                      local_change=True, remote_change=True):
        """Function to apply changes to local file, remote or both
        """
        # create a conflict by changing a file in both locations
        last_index = proj.index
        # find a text file
        for asset in last_index:
            if asset['path'].endswith(filename):
                break
        path = asset['full_path']
        if constants.PY3:
            mode = 'at'
        else:
            mode = 'ab'

        if remote_change:
            # modify it with no change to local date_modified
            # (create a copy, modify, upload and delete copy)
            shutil.copy(path, 'tmp.txt')

            osf_asset = copy.copy(proj.osf.find_asset(asset['path']))
            osf_asset['full_path'] = 'tmp.txt'
            with open('tmp.txt', mode) as f:
                f.write("A bit of text added remotely. ")
            proj.osf.add_file(osf_asset, update=True)
            os.remove('tmp.txt')  # delete the copy used for secret edit

        if local_change:
            # change again locally
            with open(path, mode) as f:
                f.write("A bit of text added locally. ")

if __name__ == "__main__":
    try:
        from psychopy import logging
        console = logging.console
    except ImportError:
        import logging
        console = logging.getLogger()
    console.setLevel(logging.INFO)
    import pytest
    # pytest.main(args=[__file__+"::TestProjectChanges::test_folder_in_folder", '-s'])
    pytest.main(args=[__file__, '-s'])
