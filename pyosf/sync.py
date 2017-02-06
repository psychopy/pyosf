# -*- coding: utf-8 -*-
"""The functions to perform the sync itself given a pair of file
listings (remote and local) and a copy of the previous state (db)

Part of the pyosf package
https://github.com/psychopy/pyosf/

Released under MIT license

Created on Sun Feb  7 21:31:15 2016

@author: lpzjwp
"""
from __future__ import absolute_import, print_function
from .constants import SHA
import copy
import os
import shutil
import weakref
try:
    from psychopy import logging
except ImportError:
    import logging
from .tools import dict_from_list

"""
Resolutions table
search for e.g. code:010 to find the relevant python resolution
+-------+-------+--------+-------------------------------------------+
| index | local | remote |                  action                   |
+-------+-------+--------+-------------------------------------------+
|     1 |     1 |      1 | check sha for file changes                |
|     1 |     0 |      0 | remove from index                         |
|     1 |     1 |      0 | if loc mod since last sync then recreate  |
|     1 |     0 |      1 | if rem mod since last sync then recreate  |
|       |       |        |                                           |
|     0 |     1 |      1 | check sha and modified date               |
|     0 |     1 |      0 | create on remote                          |
|       |       |        |                                           |
|     0 |     0 |      1 | create on local                           |
+-------+-------+--------+-------------------------------------------+
"""


class Changes(object):
    """This is essentially a dictionary of lists
    """
    def __init__(self, proj):
        self.proj = weakref.ref(proj)
        # make sure indices are up to date
        proj.local.rebuild_index()
        proj.osf.rebuild_index()
        # create the names of the self attributes
        # the actual attributes will be created during _set_empty
        self._change_types = []
        # order is determined by the conflict cases (requires most change)
        for action in ['add', 'mv', 'update', 'del']:
            for target in ['local', 'remote']:
                self._change_types.append("{}_{}".format(action, target))
        self._set_empty()
        self.local_index = proj.local.index
        self.remote_index = proj.osf.index
        self.last_index = proj.index
        self.analyze()
        self._status = 0

    def __str__(self):
        s = "\t Add\t Del\t Mv\t Update\n"
        for kind in ['local', 'remote']:
            s += "{}\t {:n}\t {:n}\t {:n}\t {:n}\n".format(
                kind,
                len(getattr(self, "add_{}".format(kind))),
                len(getattr(self, "del_{}".format(kind))),
                len(getattr(self, "mv_{}".format(kind))),
                len(getattr(self, "update_{}".format(kind))),
                )
        return s

    def __len__(self):
        return len(self.dry_run())

    def _set_empty(self):
        for attrib_name in self._change_types:
            setattr(self, attrib_name, {})

    def _make_dirs(self, path):
        """Replaces os.makedirs by keeping tack of what folders we added
        """
        root = path
        to_add = []
        print("DoingMakeDirs for {}".format(path))
        # find how low we have to go before valid path found
        while not os.path.isdir(root):
            root, needed = os.path.split(root)
            to_add.insert(0, needed)  # insert at beginning to add first
            if root=='' or needed=='':
                break  # we got to either "/" or "path" 
        # now create those folder rescursively from bottom
        for this_folder in to_add:
            root = os.path.join(root, this_folder)
            os.mkdir(root)
            self.add_to_index(root)  # update the index with this new folder
            print("AddedFolder {}".format(root))
        
    def apply_add_local(self, asset, new_path=None, threaded=False):
        proj = self.proj()
        full_path = os.path.join(proj.local.root_path, new_path)

        # handle folders
        if asset['kind'] == "folder":
            if os.path.isdir(full_path):
                self.add_to_index(full_path)  # make sure its in index
                return 1  # the folder may have been created implicitly already
            else:
                self._make_dirs(full_path)
                logging.info("Sync.Changes: created folder: {}"
                             .format(full_path))
                return 1  # the folder may have been created implicitly already

        # this is a file
        container, filename = os.path.split(full_path)
        if not os.path.isdir(container):
            self._make_dirs(container)
        proj.osf.session.download_file(asset['url'], full_path,
                                       size=asset['size'],
                                       threaded=threaded, changes=self)
        logging.info("Sync.Changes request: File download: {}"
                     .format(new_path))
        return 1

    def apply_add_remote(self, asset, new_path=None, threaded=False):
        proj = self.proj()
        if new_path in proj.osf.containers:
            # this has already handled (e.g. during prev file upload)
            return 1
        elif new_path is not None:
            asset = copy.copy(asset)
            asset['path'] = new_path
        if asset['kind'] == 'folder':
            proj.osf.add_container(asset['path'], kind='folder', changes=self)
            logging.info("Sync.Changes request: Create folder: {}"
                         .format(new_path))
        else:
            proj.osf.add_file(asset, threaded=threaded, changes=self)
            logging.info("Sync.Changes request: File upload: {}"
                         .format(new_path))
        return 1

    def apply_mv_local(self, asset, new_path, threaded=False):
        if asset['kind'] == 'folder':
            return 1
            
        proj = self.proj()
        full_path_new = os.path.join(proj.local.root_path, new_path)
        full_path_old = os.path.join(proj.local.root_path, asset['path'])
        # check if folder exists:
        new_folder = os.path.split(full_path_new)[0]
        if not os.path.isdir(new_folder):
            self._make_dirs(new_folder)
        shutil.move(full_path_old, full_path_new)
        self.rename_in_index(asset, new_path)
        logging.info("Sync.Changes done: Moved file locally: {} -> {}"
                     .format(asset['full_path'], new_path))
        return 1

    def apply_mv_remote(self, asset, new_path, threaded=False):
        proj = self.proj()
        new_folder, new_name = os.path.split(new_path)
        proj.osf.rename_file(asset, new_path, changes=self)
        logging.info("Sync.Changes request: Move file remote: {} -> {}"
                     .format(asset['path'], new_path))
        return 1

    def apply_del_local(self, asset, new_path=None, threaded=False):
        proj = self.proj()
        full_path = os.path.join(proj.local.root_path, new_path)
        if os.path.isfile(full_path):  # might have been removed already?
            os.remove(full_path)
        if os.path.isdir(full_path):  # might have been removed already?
            os.rmdir(full_path)
        logging.info("Sync.Changes done: Removed file locally: {}"
                     .format(asset['path']))
        self.remove_from_index(asset['path'])
        return 1

    def apply_del_remote(self, asset, new_path=None, threaded=False):
        proj = self.proj()
        proj.osf.del_file(asset, changes=self)
        logging.info("Sync.Changes request: Remove file remotely: {}"
                     .format(asset['path']))
        return 1

    def apply_update_local(self, asset, new_path=None, threaded=False):
        proj = self.proj()
        full_path = os.path.join(proj.local.root_path, asset['path'])
        # remove previous copy of file
        if os.path.isfile(full_path):  # might have been removed already?
            os.remove(full_path)
            self.remove_from_index(asset['path'])
        # then fetch new one from remote
        proj.osf.session.download_file(asset['url'], full_path,
                                       size=asset['size'],
                                       threaded=threaded, changes=self)
        logging.info("Sync.Changes request: Update file locally: {}"
                     .format(asset['path']))
        return 1

    def apply_update_remote(self, asset, new_path=None, threaded=False):
        proj = self.proj()
        proj.osf.add_file(asset, update=True,
                          threaded=threaded, changes=self)
        logging.info("Sync.Changes request: Update file remotely: {}"
                     .format(new_path))
        return 1

    def _asset_from_path(self, path):
        """Try to find asset and return it
        """
        root = self.proj().root_path
        if path.startswith(root):
            path = path.replace(root, '')
            while path.startswith('/'):
                path = path[1:]
        path = path.replace(self.proj().root_path, '')
        local_dict = dict_from_list(self.local_index, 'path')
        last_dict = dict_from_list(self.last_index, 'path')
        remote_dict = dict_from_list(self.remote_index, 'path')
        if path in local_dict:
            return local_dict[path]
        elif path in last_dict:
            return last_dict[path]
        elif path in remote_dict:
            return remote_dict[path]
        else:
            for ky in remote_dict.keys():
                print('  - {}, '.format(ky, remote_dict[ky]['path']))
            return 0  # fail

    def add_to_index(self, path):
        """Tries to find the asset from the path to delete it

        Path is ideally a local path (which acts as a key to the asset in
        the local index) but if it's a URL we'll try to deduce the local path
        """
        asset = self._asset_from_path(path)
        if asset:
            self.last_index.append(asset)
            return 1  # success
        else:
            logging.error("Was asked to add {} to index but "
                          "it wasn't found. That could lead to corruption."
                          .format(path))
            return 0  # fail

    def remove_from_index(self, path):
        asset = self._asset_from_path(path)
        if asset:
            self.last_index.remove(asset)
            return 1  # success
        else:
            logging.error("Was asked to remove {} from index but "
                          "it wasn't found. That could lead to corruption."
                          .format(path))
            return 0  # fail


    def rename_in_index(self, asset, new_path):
        last_dict = dict_from_list(self.last_index, 'path')
        if asset['path'] in last_dict:
            new_asset = last_dict[asset['path']]
            new_asset['path'] = new_path
            return 1
        else:
            logging.error("Was asked to remove {} from index but "
                          "it wasn't in index. That could lead to corruption."
                          .format(asset['path']))
            return 0


    def apply(self, threaded=False, dry_run=False):
        """Apply the changes using the given remote.Session object
        returns a list of strings about what happened (or will happen if
        dry_run=True)
        """
        proj = self.proj()
        self._status = 1
        actions = []
        # would it be wise to perform del operations before others?
        for action_type in self._change_types:
            action_dict = getattr(self, action_type)
            path_list = list(action_dict.keys())  # for Python3 convert to list
            # sort by path
            if action_type[:3] in ['del', 'mv_']:
                reverse = True  # so folders deleted last
            else:
                reverse = False  # so folders created first
            path_list.sort(reverse=reverse)
            # get the self.apply___() function to be applied
            func_apply = getattr(self, "apply_{}".format(action_type))
            for new_path in path_list:
                asset = action_dict[new_path]
                if dry_run:
                    actions.append("{}: {}".format(action_type, new_path))
                else:
                    func_apply(asset, new_path, threaded=threaded)
        if not dry_run:
            proj.local._needs_rebuild_index = True
            if threaded:
                proj.osf.session.apply_changes()  # starts the up/downloads
            else:
                self.finish_sync()
        return actions

    def dry_run(self):
        """Doesn't do anything but returns a list of strings describing the
        actions
        """
        return self.apply(dry_run=True)

    @property
    def progress(self):
        """Returns the progress of changes:
            0 for not started sync (need apply())
            dict during sync {'up':[done, total], 'down':[done, total]}
            1 for finished
        """
        if self._status in [0, -1]:  # not started or had already finished
            return self._status
        # otherwise we're partway through sync so check with session
        prog = self.proj().osf.session.get_progress()
        if prog == 1:
            self._status = -1  # was running but now finished
        else:
            self._status = 1  # running
        return prog  # probably a dictionary

    def finish_sync(self):
        """Rebuilds index and saves project file when the sync has finished
        """
        proj = self.proj()
        # when local/remote updates are complete refresh index based on local
        proj.local.rebuild_index()
        # proj.index = proj.local.index
        self._set_empty()
        proj.save()
        if hasattr(logging, 'flush'):  # psychopy.logging has control of flush
            logging.flush()

    def analyze(self):
        """Take a list of files
        """
        local = self.local_index
        remote = self.remote_index
        index = self.last_index
        # copies of the three asset lists.
        # Safe to alter these only at top level
        local_p = dict_from_list(local, 'path')
        remote_p = dict_from_list(remote, 'path')
        index_p = dict_from_list(index, 'path')

        # go through the files in the database
        for path, asset in index_p.items():
            # code:1xx all these files existed at last sync
            if path in remote_p.keys() and path in local_p.keys():
                # code:111
                # Still exists in all. Check for local/remote modifications
                local_asset = local_p[path]
                remote_asset = remote_p[path]

                if asset['kind'] == 'folder':
                    # for folders check /contents/ not folder itself
                    logging.debug("Sync.analyze 111a: {} no action"
                                  .format(path))

                elif asset[SHA] == remote_asset[SHA] and \
                        asset[SHA] == local_asset[SHA]:
                    # all copies match. Go and have a cup of tea.
                    logging.debug("Sync.analyze 111b: {} no action"
                                  .format(path))

                elif asset[SHA] != remote_asset[SHA] and \
                        asset[SHA] != local_asset[SHA]:
                    # both changed. Conflict!
                    local_time = local_asset['date_modified']
                    remote_time = remote_asset['date_modified']
                    local_path, remote_path = conflict_paths(path, local_time,
                                                             remote_time)
                    # rename the remote and local files with CONFLICT tag
                    self.mv_local[local_path] = local_asset
                    self.mv_remote[remote_path] = remote_asset
                    # and swap the version from the other side
                    self.add_local[remote_path] = remote_asset
                    self.add_remote[local_path] = local_asset
                    logging.info("Sync.analyze 111c: {} conflict"
                                 "(changed on local and remote)"
                                 .format(path))

                elif asset[SHA] != remote_asset[SHA]:
                    # changed remotely only
                    # TODO: we know the files differ and we presume the remote
                    # is the newer one. Could check the date_modified?
                    # But if they differed wouldn't that mean a clock err?
                    self.update_local['path'] = remote_asset
                    logging.info("Sync.analyze 111d: {} changed remotely"
                                 .format(path))

                elif asset[SHA] != local_asset[SHA]:
                    # changed locally only
                    # TODO: we know the files differ and we presume the local
                    # is the newer one. Could check the date_modified?
                    # But if they differed wouldn't that mean a clock err?
                    # fetch the links from the remote so we can do an update op
                    local_asset['links'] = remote_asset['links']
                    self.update_remote['path'] = local_asset
                    logging.info("Sync.analyze 111e: {} changed locally"
                                 .format(path))

                # don't re-analyze
                del local_p[path]
                del remote_p[path]

            elif path not in remote_p.keys() and path not in local_p.keys():
                # code:100
                # Was deleted in both. Remove from index
                logging.debug("Sync.analyze 100: {}"
                              "deleted locally and remotely"
                              .format(path))
                self.remove_from_index(path)

            elif path not in local_p.keys():
                remote_asset = remote_p[path]
                # code:101 has been deleted locally but exists remotely
                if asset['date_modified'] < remote_asset['date_modified']:
                    # deleted locally but changed on remote. Recreate
                    # make new path and get the newer asset info
                    new_path = recreated_path(path)
                    # remote: rename (move) to include "_DELETED"
                    # local: just add the new asset with new path
                    self.add_local[new_path] = remote_asset
                    self.mv_remote[new_path] = remote_asset
                    logging.warn("Sync.analyze 101a: {} conflict "
                                  "(deleted locally and changed remotely)"
                                  .format(path))
                else:
                    # deleted locally unchanged remotely. Delete remotely
                    self.del_remote[asset['path']] = remote_asset
                    logging.info("Sync.analyze 101b: {}  "
                                  "deleted locally (and unchanged remotely)"
                                  .format(path))
                del remote_p[path]  # remove so we don't re-analyze

            elif path not in remote_p.keys():
                # has been deleted remotely but exists locally
                # code:110
                local_asset = local_p[path]
                if asset['date_modified'] < local_asset['date_modified']:
                    # deleted remotely but changed on local. Recreate
                    # make new path and get the newer asset info
                    new_path = recreated_path(path)
                    # remote: rename (move) to include "_DELETED"
                    self.mv_local[new_path] = local_asset
                    # local: just add the new asset with new path
                    self.add_remote[new_path] = local_asset
                    logging.warn("Sync.analyze 110a: {} conflict "
                                  "(deleted remotely unchanged locally)"
                                  .format(path))
                else:
                    # deleted remotely unchanged locally. Delete locally
                    self.del_local[asset['path']] = asset
                    logging.info("Sync.analyze 110b: {} "
                                 "deleted remotely (and unchanged locally)"
                                 .format(path))
                del local_p[path]  # remove so we don't re-analyse

        # go through the files in the local
        for path, local_asset in local_p.items():
            # code:01x we know these files aren't in index but are local
            if path in remote_p.keys():
                if local_asset['kind'] == 'folder':  # if folder then leave
                    continue
                # TODO: do we need to handle the case that the user creates a
                # folder in one place and file in another with same names?!
                remote_asset = remote_p[path]
                # code:011
                if remote_asset[SHA] == local_asset[SHA]:
                    # both copies match but not in index (user uplaoded?)
                    logging.debug("Sync.analyze 011a: {} "
                                  "added remotely and locally (identical file)"
                                  .format(path))
                del remote_p[path]
            else:
                # code:010
                self.add_remote[path] = local_asset
                logging.info("Sync.analyze 010a: {} added locally"
                             .format(path))

        # go through the files in the remote
        for path, remote_asset in remote_p.items():
            # code:001 has been created remotely
            self.add_local[path] = remote_asset
            logging.info("Sync.analyze 001a: {} added remotely"
                         .format(path))


def recreated_path(path):
    """If we have to add a file back (that was deleted) then add RECREATED to
    the name
    """
    root, ext = os.path.splitext(path)
    return root+"_DELETED"+ext


def conflict_paths(path, local_time, server_time):
    """
    """
    root, ext = os.path.splitext(path)
    local = "{}_CONFLICT{}{}".format(root, local_time, ext)
    server = "{}_CONFLICT{}{}".format(root, server_time, ext)
    return local, server


def _update_path(asset, new_path=None):
    """Helper function to check whether path *in* the dict matches the key
    """
    if new_path is None:
        new_path = asset['path']
    elif new_path != asset['path']:
        asset = copy.copy(asset)  # update a new copy
        asset['path'] = new_path
    return new_path, asset
