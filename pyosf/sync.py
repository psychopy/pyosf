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
    def __init__(self, local_index, remote_index, last_index):
        # create the names of the self attributes
        # the actual attributes will be created during _set_empty
        self._change_types = []
        # order is determined by the conflict cases (requires most change)
        for action in ['add', 'mv', 'update', 'del']:
            for target in ['local', 'remote']:
                self._change_types.append("{}_{}".format(action, target))
        self._set_empty()
        self.local_index = local_index
        self.remote_index = remote_index
        self.last_index = last_index
        self.analyze()

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

    def _set_empty(self):
        for attrib_name in self._change_types:
            setattr(self, attrib_name, {})

    def apply_add_local(self, proj, asset, new_path=None):
        full_path = os.path.join(proj.local.root_path, new_path)

        # handle folders
        if asset['kind'] == "folder":
            if os.path.isdir(full_path):
                return 1  # the folder may have been created implicitly already
            else:
                os.makedirs(full_path)
                return 1  # the folder may have been created implicitly already

        # this is a file
        container, filename = os.path.split(full_path)
        if not os.path.isdir(container):
            os.makedirs(container)
        proj.osf.session.download_file(asset['id'], full_path)
        logging.info("Added file to local: {}".format(full_path))
        if hasattr(logging, 'flush'):
            logging.flush()
        return 1

    def apply_add_remote(self, proj, asset, new_path=None):
        if new_path in proj.osf.containers:
            # this has already handled (e.g. during prev file upload)
            return 1
        elif new_path is not None:
            asset = copy.copy(asset)
            asset['path'] = new_path
        if asset['kind'] == 'folder':
            proj.osf.add_container(asset['path'], kind='folder')
        else:
            proj.osf.add_file(asset)
        logging.info("Added {} to remote: {}".format(asset['kind'], new_path))
        return 1

    def apply_mv_local(self, proj, asset, new_path):
        full_path_new = os.path.join(proj.local.root_path, new_path)
        full_path_old = os.path.join(proj.local.root_path, asset['path'])
        shutil.move(full_path_old, full_path_new)
        asset['path'] = new_path
        logging.info("Sync: Moved file locally: {} -> {}"
                     .format(asset['full_path'], new_path))
        return 1

    def apply_mv_remote(self, proj, asset, new_path):
        new_folder, new_name = os.path.split(new_path)
        proj.osf.rename_file(asset, new_path)
        logging.info("Sync: Moved file remote: {} -> {}"
                     .format(asset['path'], new_path))
        return 1

    def apply_del_local(self, proj, asset, new_path=None):
        full_path = os.path.join(proj.local.root_path, new_path)
        if os.path.isfile(full_path):  # might have been removed already?
            os.remove(full_path)
        if os.path.isdir(full_path):  # might have been removed already?
            os.rmdir(full_path)
        logging.info("Removed file locally: {}".format(asset['path']))
        return 1

    def apply_del_remote(self, proj, asset, new_path=None):
        proj.osf.del_file(asset)
        logging.info("Sync: Del file remote: {}"
                     .format(asset['path']))
        return 1

    def apply_update_local(self, proj, asset, new_path=None):
        full_path = os.path.join(proj.local.root_path, asset['path'])
        # remove previous copy of file
        if os.path.isfile(full_path):  # might have been removed already?
            os.remove(full_path)
        # then fetch new one from remote
        proj.osf.session.download_file(asset['id'], full_path)
        return 1

    def apply_update_remote(self, proj, asset, new_path=None):
        proj.osf.add_file(asset, update=True)
        logging.info("Sync: Update file remote: {}".format(asset['path']))
        return 1

    def apply(self, proj):
        """Apply the changes using the given remote.Session object
        """
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
                func_apply(proj, asset, new_path)
        # when local/remote updates are complete refresh index based on local
        proj.local.rebuild_index()
        proj.index = proj.local.index
        self._set_empty()

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
                    pass  # for folders check /contents/ not folder itself

                elif asset[SHA] == remote_asset[SHA] and \
                        asset[SHA] == local_asset[SHA]:
                    # all copies match. Go and have a cup of tea.
                    pass

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

                elif asset[SHA] != remote_asset[SHA]:
                    # changed remotely only
                    # TODO: we know the files differ and we presume the remote
                    # is the newer one. Could check the date_modified?
                    # But if they differed wouldn't that mean a clock err?
                    self.update_local['path'] = remote_asset

                elif asset[SHA] != local_asset[SHA]:
                    # changed locally only
                    # TODO: we know the files differ and we presume the local
                    # is the newer one. Could check the date_modified?
                    # But if they differed wouldn't that mean a clock err?
                    # fetch the links from the remote so we can do an update op
                    local_asset['links'] = remote_asset['links']
                    self.update_remote['path'] = local_asset

                # don't re-analyze
                del local_p[path]
                del remote_p[path]

            elif path not in remote_p.keys() and path not in local_p.keys():
                # code:100
                # Was deleted in both. Forget about it
                pass

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
                else:
                    # deleted locally unchanged remotely. Delete remotely
                    self.del_remote[asset['path']] = remote_asset
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
                else:
                    # deleted remotely unchanged locally. Delete locally
                    self.del_local[asset['path']] = asset
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
                    pass  # nothing to do
                del remote_p[path]
            else:
                # code:010
                self.add_remote[path] = local_asset

        # go through the files in the remote
        for path, remote_asset in remote_p.items():
            # code:001 has been created remotely
            self.add_local[path] = remote_asset


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
