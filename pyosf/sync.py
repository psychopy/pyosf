# -*- coding: utf-8 -*-
"""
These are the functions to perform the sync itself given a pair of file
listings (remote and local) and a copy of the previous state (db)

Created on Sun Feb  7 21:31:15 2016

@author: lpzjwp
"""
from __future__ import absolute_import, print_function
from .constants import SHA
import copy
import os
try:
    from psychopy import logging
except ImportError:
    import logging

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


def dict_from_list(in_list, key):
    """From a list of dicts creates a dict of dicts using a given key name
    """
    d = {}
    for entry in in_list:
        d[entry[key]] = entry
    return d


class Changes(object):

    def __init__(self):
        self._set_empty()

    def __str__(self):
        s = "\t Add\t Del\t Mv\t Update\n"
        for kind in ['local', 'remote', 'index']:
            s += "{}\t {:n}\t {:n}\t {:n}\t {:n}\n".format(
                kind,
                len(getattr(self, "add_{}".format(kind))),
                len(getattr(self, "del_{}".format(kind))),
                len(getattr(self, "mv_{}".format(kind))),
                len(getattr(self, "update_{}".format(kind))),
                )
        return s

    def _set_empty(self):
        self.add_local = {}
        self.del_local = {}
        self.mv_local = {}   # mv is rename
        self.update_local = {}
        self.add_remote = {}
        self.del_remote = {}
        self.mv_remote = {}
        self.update_remote = {}
        self.add_index = {}
        self.del_index = {}
        self.mv_index = {}
        self.update_index = {}

    def apply_add_local(self, proj, asset, new_path=None):
        full_path = os.path.join(proj.local.root_path, new_path)

        # handle folders
        if asset['kind'] == "folder":
            if os.path.isdir(full_path):
                return 1  # the folder may have been created implicitly already
            else:
                os.makedirs(full_path)

        # this is a file
        folder_path, filename = os.path.split(full_path)
        if not os.path.isdir(folder_path):
            os.makedirs(folder_path)
        proj.osf.session.download_file(asset['id'], full_path)
        logging.info("Added local file: {}".format(full_path))
        if hasattr(logging, 'flush'):
            logging.flush()

    def apply_add_remote(self, proj, asset, new_path=None):
        pass  # TODO:

    def apply_add_index(self, proj, asset, new_path=None):
        pass  # TODO:

    def apply_mv_local(self, proj, asset, new_path):
        pass  # TODO: # NB asset will have old path

    def apply_mv_remote(self, proj, asset, new_path):
        pass  # TODO:  # NB asset will have old path

    def apply_mv_index(self, proj, asset, new_path):
        pass  # TODO:  # NB asset will have old path

    def apply_del_local(self, proj, asset, new_path=None):
        pass  # TODO:

    def apply_del_remote(self, proj, asset, new_path=None):
        pass  # TODO:

    def apply_del_index(self, proj, asset, new_path=None):
        pass  # TODO:

    def apply_update_local(self, proj, asset):
        pass  # TODO:

    def apply_update_remote(self, proj, asset):
        pass  # TODO:

    def apply_update_index(self, proj, asset):
        pass  # TODO:

    def apply(self, proj):
        """Apply the changes using the given remote.Session object
        """
        # would it be wise to perform del operations before others?
        for action_type in dir(self):
            if "apply_{}".format(action_type) in dir(self):
                func_apply = getattr(self, "apply_{}".format(action_type))
                for new_path, asset in getattr(self, action_type).items():
                    func_apply(proj, asset, new_path)

        self._set_empty()


def recreated_path(path):
    """If we have to add a file back (that was deleted) then add RECREATED to
    the name
    """
    root, ext = os.path.splitext(path)
    return root+"_DELETED."+ext


def conflict_paths(path, local_time, server_time):
    """
    """
    root, ext = os.path.splitext(path)
    local = "{}_CONFLICT{}.{}".format(root, local_time, ext)
    server = "{}_CONFLICT{}.{}".format(root, server_time, ext)
    return local, server


def get_changes(local, remote, index):
    """Take a list of files
    """
    # copies of the three asset lists. Safe to alter these only at top level
    local_p = dict_from_list(local, 'path')
    remote_p = dict_from_list(remote, 'path')
    index_p = dict_from_list(index, 'path')
    changes = Changes()

    # go through the files in the database
    for path, asset in index_p.items():
        # code:1xx all these files existed at last sync
        if path in remote_p.keys() and path in local_p.keys():
            # code:111
            # Still exists in all. Check for local/remote modifications
            local_asset = local_p[path]
            remote_asset = remote_p[path]

            if asset[SHA] == remote_asset[SHA] and \
                    asset[SHA] == local_asset[SHA]:
                # all copies match. Go and have a cup of tea.
                pass

            elif asset[SHA] != remote_p[path][SHA] and \
                    asset[SHA] != local_p[path][SHA]:
                # both changed. Conflict!
                local_time = local_asset['time_modified']
                remote_time = remote_asset['time_modified']
                local_path, remote_path = conflict_paths(path, local_time,
                                                         remote_time)
                # rename the remote and local files with CONFLICT tag
                changes.mv_local[local_path] = local_asset
                changes.mv_remote[remote_path] = remote_asset
                # and swap the version from the other side
                changes.add_local[remote_path] = remote_asset
                changes.add_remote[local_path] = local_asset
                # and update index
                changes.del_index[asset['path']] = asset
                changes.add_index[remote_path] = remote_asset
                changes.add_index[local_path] = local_asset

            elif asset[SHA] != remote_p[path][SHA]:
                # changed remotely only
                # TODO: we know the files differ and we presume the remote
                # is the newer one, but should we be checking the dat_modified?
                # But if they differed wouldn't that mean a clock err?
                changes.update_local['path'] = remote_asset
                changes.update_index['path'] = remote_asset

            elif asset[SHA] != local_p[path][SHA]:
                # changed locally only
                # TODO: we know the files differ and we presume the local
                # is the newer one, but should we be checking the dat_modified?
                # But if they differed wouldn't that mean a clock err?
                changes.update_remote['path'] = local_asset
                changes.update_index['path'] = local_asset

            # don't re-analyze
            del local_p[path]
            del remote_p[path]

        elif path not in remote_p.keys() and path not in local_p.keys():
            # code:100
            # Was deleted in both. Safe to remove from index
            changes.del_index(asset)

        elif path not in local_p.keys():
            # code:101 has been deleted locally but exists remotely
            if asset['date_modified'] < remote_p[path]['date_modified']:
                # deleted locally but changed on remote. Recreate
                # make new path and get the newer asset info
                new_path = recreated_path(path)
                new_asset = remote_p[path]
                # remote: rename (move) to include "_DELETED"
                changes.mv_remote[new_path] = new_asset
                # index: remove old asset and add new one
                changes.del_index[asset['path']] = asset
                changes.add_index[new_path] = new_asset
                # local: just add the new asset with new path
                changes.add_local[new_path] = new_asset
            else:
                # deleted locally unchanged remotely. Delete in both
                changes.rem_index[asset['path']] = asset
                changes.rem_remote[asset['path']] = asset
            del remote_p[path]  # remove so we don't re-analyze

        elif path not in remote_p.keys():
            # has been deleted remotely but exists locally
            # code:110
            if asset['date_modified'] < local_p[path]['date_modified']:
                # deleted remotely but changed on local. Recreate
                # make new path and get the newer asset info
                new_path = recreated_path(path)
                new_asset = local_p[path]
                # remote: rename (move) to include "_DELETED"
                changes.mv_local[new_path] = new_asset
                # index: remove old asset and add new one
                changes.del_index[asset['path']] = asset
                changes.add_index[new_path] = new_asset
                # local: just add the new asset with new path
                changes.add_remote[new_path] = new_asset
            else:
                # deleted remotely unchanged locally. Delete in both
                changes.rem_index[asset['path']] = asset
                changes.rem_local[asset['path']] = asset
            del local_p[path]  # remove so we don't re-analyse

    # go through the files in the local
    for path, local_asset in local_p.items():
        # code:01x we know these files aren't in index but are local
        if path in remote_p.keys():
            remote_asset = remote_p[path]
            # code:011
            if remote_asset[SHA] == local_asset[SHA]:
                # both copies match but not in index (user manually uplaoded?)
                changes.add_index[path] = local_asset
        else:
            # code:010
            changes.add_index[path] = local_asset
            changes.add_remote[path] = local_asset

    # go through the files in the remote
    for path, remote_asset in remote_p.items():
        # code:001 has been created remotely
        changes.add_index[path] = remote_asset
        changes.add_local[path] = remote_asset

    return changes


def _update_path(asset, new_path=None):
    """Helper function to check whether path *in* the dict matches the key
    """
    if new_path is None:
        new_path = asset['path']
    elif new_path != asset['path']:
        asset = copy.copy(asset)  # update a new copy
        asset['path'] = new_path
    return new_path, asset
