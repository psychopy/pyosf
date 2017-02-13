# -*- coding: utf-8 -*-
"""Classes and functions to access remote (https://OSF.io) projects

Part of the pyosf package
https://github.com/psychopy/pyosf/

Released under MIT license

Created on Sun Feb  7 21:31:15 2016

@author: lpzjwp
"""

from __future__ import absolute_import, print_function

import os
import weakref
import requests
import threading
import json
import datetime
import time
import hashlib
try:
    from psychopy import logging
except ImportError:
    import logging
from . import constants
from .tools import dict_from_list, find_by_key
from . import exceptions

# for the status of the PushPullThread
NOT_STARTED = 0
STARTED = 1
FINISHED = -1

default_chunk_size = 65536  # 65Kb


class TokenStorage(dict):
    """Dict-based class to store all the known tokens according to username
    """
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.load()

    def load(self, filename=None):
        """Load all tokens from a given filename
        (defaults to ~/.pyosf/tokens.json)
        """
        if filename is None:
            filename = os.path.join(constants.PYOSF_FOLDER, 'tokens.json')
        if os.path.isfile(filename):
            with open(filename, 'r') as f:
                try:
                    self.update(json.load(f))
                except ValueError:
                    pass  # file didn't contain valid json data

    def save(self, filename=None):
        """Save all tokens from a given filename
        (filename defaults to ~/.pyosf/tokens.json)
        """
        if filename is None:
            filename = os.path.join(constants.PYOSF_FOLDER, 'tokens.json')
        if not os.path.isdir(constants.PYOSF_FOLDER):
            os.makedirs(constants.PYOSF_FOLDER)
        with open(filename, 'wb') as f:
            json_str = json.dumps(self)
            if constants.PY3:
                f.write(bytes(json_str, 'UTF-8'))
            else:
                f.write(json_str)


class BufferReader(object):
    """requests doesn't have a method for uploading files in chunks so this
    class provides that by simulating a file.read method but using chunks
    (and tracking how much has been sent)
    """
    def __init__(self, filepath, chunk_size=default_chunk_size, callback=None):
        self._callback = callback
        self._progress = 0
        self.chunk_size = chunk_size
        self._len = os.path.getsize(filepath)
        self._f = open(filepath, 'rb')

    def __len__(self):
        return self._len

    def read(self, chunk_size):
        chunk = self._f.read(chunk_size)
        self._progress += int(len(chunk))  # len of actual chunk, not requested
        time.sleep(0.0001)
        if self._callback:
            try:
                self._callback(self._progress)
            except:  # catches exception from the callback
                raise exceptions.CancelledError('The upload was cancelled.')
        return chunk


class PushPullThread(threading.Thread):
    def __init__(self, session, kind='push',
                 chunk_size=default_chunk_size,
                 finished_callback=None,
                 changes=None):  # 65Kb
        threading.Thread.__init__(self)
        self.finished_callback = finished_callback
        self.asset_list = []
        self.status = NOT_STARTED
        self.session = weakref.ref(session)
        self.chunk_size = chunk_size
        self.queue_size = 0
        self._finished_files_size = 0
        self.this_file_prog = 0
        self.kind = kind
        if changes:
            self.changes = weakref.ref(changes)  # a changes tracking object
        else:
            self.changes = None

    @property
    def finished_size(self):
        return self._finished_files_size + self.this_file_prog

    def add_asset(self, url, local_path, size):
        self.asset_list.append(
            {'url': url,
             'local_path': local_path,
             'size': size})
        self.queue_size += size

    def run(self):
        self.status = STARTED  # probably can't be read so don't bother?
        session = self.session()  # session is a self.weakref
        if self.kind == 'push':
            for asset in self.asset_list:
                self.upload_file(asset, session)
        else:
            for asset in self.asset_list:
                self.download_file(asset, session)
                logging.info("Downloading {} from {}"
                             .format(asset['local_path'], asset['url']))
        self.status = FINISHED
        if self.finished_callback:
            self.finished_callback()

    def info_callback(self, progress):
        self.this_file_prog = progress

    def upload_file(self, asset, session):
        self.currFileProgress = 0
        # do the upload
        time.sleep(0.1)
        if asset['size'] > 1000000:  # bigger than 1mb uses chunking
            file_buffer = BufferReader(asset['local_path'],
                                       self.chunk_size, self.info_callback)
            reply = session.put(asset['url'], data=file_buffer, timeout=30.0)
        else:
            with open(asset['local_path'], 'rb') as file_buffer:
                reply = session.put(asset['url'], data=file_buffer,
                                    timeout=30.0)
        # check the upload worked (md5 checksum)
        with open(asset['local_path'], 'rb') as f:
            local_md5 = hashlib.md5(f.read()).hexdigest()
        if reply.status_code not in [200, 201]:
            raise exceptions.HTTPSError(
                "URL:{}\nreply:{}"
                .format(asset['url'], json.dumps(reply.json(), indent=2)))
        # reply includes info about the FileNode created so process that
        uploadedAttrs = reply.json()['data']['attributes']
        if local_md5 != uploadedAttrs['extra']['hashes']['md5']:
            raise exceptions.OSFError("Uploaded file did not match existing "
                                      "SHA. Maybe it didn't fully upload?")
        self._finished_files_size += asset['size']
        logging.info("Async upload complete: {} to {}"
                     .format(asset['local_path'], asset['url']))
        if self.changes:  # a weak ref to changes object. Update index
            self.changes().add_to_index(asset['local_path'])  # signals success

    def download_file(self, asset, session):
        self.this_file_prog = 0
        reply = session.get(asset['url'], stream=True, timeout=30.0)
        if reply.status_code == 200:
            with open(asset['local_path'], 'wb') as f:
                for chunk in reply.iter_content(self.chunk_size):
                    f.write(chunk)
                    self.this_file_prog += self.chunk_size
                    time.sleep(0.001)
        self.this_file_prog = 0
        self._finished_files_size += asset['size']
        logging.info("Async download complete: {} to {}"
                     .format(asset['local_path'], asset['url']))
        if self.changes:  # a weak ref to changes object. Update index
            self.changes().add_to_index(asset['local_path'])  # signals success


class Session(requests.Session):
    """A class to track a session with the OSF server.

    The session will store a token, which can then be used to authenticate
    for project read/write access
    """
    def __init__(self, username=None, password=None, token=None, otp=None,
                 remember_me=True, chunk_size=default_chunk_size):
        """Create a session to send requests with the OSF server

        Provide either username and password for authentication with a new
        token, or provide a token from a previous session, or nothing for an
        anonymous user
        """
        requests.Session.__init__(self)

        self.username = username
        self.password = password
        self.user_id = None  # populate when token property is set
        self.user_full_name = None
        self.remember_me = remember_me
        self.authenticated = False
        # set token (which will update session headers as needed)
        if token is not None:
            self.token = token
        elif username is not None:
            self.authenticate(username, password, otp)
        self.headers.update({'content-type': 'application/json'})
        # placeholders for up/downloader threads
        self.downloader = None
        self.uploader = None
        self.chunk_size = default_chunk_size

    def open_project(self, proj_id):
        """Returns a OSF_Project object or None (if that id couldn't be opened)
        """
        return OSFProject(session=self, id=proj_id)

    def create_project(self, title, descr="", tags=[], public=False,
                       category='project'):
        url = "{}/nodes/".format(constants.API_BASE, self.user_id)
        if type(tags) != list:  # given a string so convert to list
            tags = tags.split(",")

        body = {
            'data': {
                'type': 'nodes',
                'attributes': {
                    'title': title,
                    'category': category,
                    'description': descr,
                    'tags': tags,
                    'public': public,
                }
            }
        }
        reply = self.post(
            url,
            data=json.dumps(body),
            headers=self.headers,
            timeout=10.0)
        if reply.status_code not in [200, 201]:
            raise exceptions.OSFError("Failed to create project at:\n  {}"
                                      .format(url))
        project_node = OSFProject(session=self, id=reply.json()['data'])
        logging.info("Successfully created project {}".format(project_node.id))
        return project_node

    def delete_project(self, id):
        """Warning, this deletes a project irreversibly
        """
        if isinstance(id, OSFProject):
            id = id.id  # we want just the id field
        url = "{}/nodes/{}/".format(constants.API_BASE, id)
        reply = self.delete(url)
        if reply.status_code == 403:
            raise exceptions.OSFError("You can only delete projects you own")
        elif reply.status_code == 204:
            logging.info("Successfully deleted project {}".format(id))
        else:
            raise exceptions.OSFError("Failed to delete project: {}\n {}:{}"
                                      .format(id, reply.status_code, reply))

    def find_projects(self, search_str, tags="psychopy"):
        """
        Parameters
        ----------
        search_str : str
            The string to search for in the title of the project
        tags : str
            Comma-separated string containing tags

        Returns
        -------
        A list of OSFProject objects

        """
        url = "{}/nodes/".format(constants.API_BASE)
        intro = "?"
        if tags:
            tagsList = tags.split(",")
            for tag in tagsList:
                tag = tag.strip()  # remove surrounding whitespace
                if tag == '':
                    continue
                url += "{}filter[tags][icontains]={}".format(intro, tag)
                intro = "&"
        if search_str:
            url += "{}filter[title][icontains]={}".format(intro, search_str)
            intro = "&"
        logging.info("Searching OSF using: {}".format(url))
        time.sleep(0.1)
        t0 = time.time()
        reply = self.get(url, timeout=30.0)
        logging.info("Download results took: {}s".format(time.time()-t0))
        t1 = time.time()
        reply = reply.json()
        logging.info("Convert JSON format took: {}s".format(time.time()-t1))
        t2 = time.time()
        projs = []
        for entry in reply['data']:
            projs.append(OSFProject(session=self, id=entry))
        logging.info("Extracting projects took: {}s".format(time.time()-t2))
        return projs

    def find_users(self, search_str):
        """Find user IDs whose name matches a given search string
        """
        reply = self.get("{}/users/?filter[full_name]={}"
                         .format(constants.API_BASE, search_str),
                         timeout=30.0).json()
        users = []
        for thisUser in reply['data']:
            attrs = thisUser['attributes']
            attrs['id'] = thisUser['id']
            users.append(attrs)
        return users

    def find_user_projects(self, user_id=None):
        """Finds all readable projects of a given user_id
        (None for current user)
        """
        if user_id is None:
            user_id = self.user_id
        full_url = "{}/users/{}/nodes?filter[category]=project" \
                   .format(constants.API_BASE, user_id)
        reply = self.get(full_url, timeout=30.0)
        if reply.status_code not in [200, 201]:
            raise exceptions.OSFError("No user found. Sent:\n   {}"
                                      .format(full_url))
        projs = []
        for entry in reply.json()['data']:
            projs.append(OSFProject(session=self, id=entry))
        return projs

    @property
    def token(self):
        """The authorisation token for the current logged in user
        """
        return self.__dict__['token']

    @token.setter
    def token(self, token, save=None):
        """Set the token for this session and check that it works for auth
        """
        self.__dict__['token'] = token
        if token is None:
            headers = {}
        else:
            headers = {
                'Authorization': 'Bearer {}'.format(token),
            }
        self.headers.update(headers)
        # then populate self.userID and self.userName
        resp = self.get(constants.API_BASE+"/users/me/", timeout=10.0)
        if resp.status_code != 200:
            raise exceptions.AuthError("Invalid credentials trying to get "
                                       "user data:\n{}".format(resp.json()))
        else:
            logging.info("Successful authentication with token")
        json_resp = resp.json()
        self.authenticated = True
        data = json_resp['data']
        self.user_id = data['id']
        self.user_full_name = data['attributes']['full_name']
        # update stored tokens
        if save is None:
            save = self.remember_me
        if save and self.username is not None:
            tokens = TokenStorage()
            tokens[self.username] = token
            tokens.save()

    def authenticate(self, username, password=None, otp=None):
        """Authenticate according to username and password (if needed).

        If the username has been used already to create a token then that
        token will be reused (and no password is required). If not then the
        password will be sent (using https) and an auth token will be stored.
        """
        # try fetching a token first
        tokens = TokenStorage()
        if username in tokens:
            logging.info("Found previous auth token for {}".format(username))
            try:
                self.token = tokens[username]
                return 1
            except exceptions.AuthError:
                if password is None:
                    raise exceptions.AuthError("User token didn't work and no "
                                               "password has been provided")
        elif password is None:
            raise exceptions.AuthError("No auth token found and no "
                                       "password given")
        token_url = constants.API_BASE+'/tokens/'
        token_request_body = {
            'data': {
                'type': 'tokens',
                'attributes': {
                    'name': '{} - {}'.format(
                        constants.PROJECT_NAME, datetime.date.today()),
                    'scopes': constants.APPLICATION_SCOPES
                }
            }
        }
        headers = {'content-type': 'application/json'}

        if otp is not None:
            headers['X-OSF-OTP'] = otp
        resp = self.post(
            token_url,
            headers=headers,
            data=json.dumps(token_request_body),
            auth=(username, password), timeout=10.0,
            )
        if resp.status_code in (401, 403):
            # If login failed because of a missing two-factor authentication
            # code, notify the user to try again
            # This header appears for basic auth requests, and only when a
            # valid password is provided
            otp_val = resp.headers.get('X-OSF-OTP', '', timeout=10.0)
            if otp_val.startswith('required'):
                raise exceptions.AuthError('Must provide code for two-factor'
                                           'authentication')
            else:
                raise exceptions.AuthError('Invalid credentials')
        elif not resp.status_code == 201:
            raise exceptions.AuthError('Invalid authorization response')
        else:
            json_resp = resp.json()
            logging.info("Successfully authenticated with username/password")
            self.authenticated = True
            self.token = json_resp['data']['attributes']['token_id']
            return 1

    def download_file(self, url, local_path,
                      size=0, threaded=False, changes=None):
        """ Download a file with given object id

        Parameters
        ----------

        asset : str or dict
            The OSF id for the file or dict of info
        local_path : str
            The full path where the file will be downloaded

        """
        if threaded:
            if self.downloader is None or \
                    self.downloader.status != NOT_STARTED:  # can't re-use
                self.downloader = PushPullThread(
                    session=self, kind='pull',
                    finished_callback=self.finished_downloads,
                    changes=changes)
            self.downloader.add_asset(url, local_path, size)
        else:
            # download immediately
            reply = self.get(url, stream=True, timeout=30.0)
            if reply.status_code == 200:
                with open(local_path, 'wb') as f:
                    for chunk in reply.iter_content(self.chunk_size):
                        f.write(chunk)
                if changes:
                    changes.add_to_index(local_path)  # signals success

    def upload_file(self, url, update=False, local_path=None,
                    size=0, threaded=False, changes=None):
        """Adds the file to the OSF project.
        If containing folder doesn't exist then it will be created recursively

        update is used if the file already exists but needs updating (version
        will be incremented).
        """
        if threaded:
            if self.uploader is None or \
                    self.uploader.status != NOT_STARTED:  # can't re-use
                self.uploader = PushPullThread(
                    session=self, kind='push',
                    finished_callback=self.finished_uploads,
                    changes=changes)
            self.uploader.add_asset(url, local_path, size)
        else:
            with open(local_path, 'rb') as f:
                reply = self.put(url, data=f, timeout=30.0)
            with open(local_path, 'rb') as f:
                local_md5 = hashlib.md5(f.read()).hexdigest()
            if reply.status_code not in [200, 201]:
                raise exceptions.HTTPSError(
                    "URL:{}\nreply:{}"
                    .format(url, json.dumps(reply.json(), indent=2)))
            node = FileNode(self, reply.json()['data'])
            if local_md5 != node.json['attributes']['extra']['hashes']['md5']:
                raise exceptions.OSFError(
                    "Uploaded file did not match existing SHA. "
                    "Maybe it didn't fully upload?")
            logging.info("Uploaded (unthreaded): ".format(local_path))
            if changes:
                changes.add_to_index(local_path)  # signals success
            return node

    def finished_uploads(self):
        self.uploader = None

    def finished_downloads(self):
        self.downloader = None

    def apply_changes(self):
        """If threaded up/downloading is enabled then this begins the process
        """
        if self.uploader:
            self.uploader.start()
        if self.downloader:
            self.downloader.start()

    def get_progress(self):
        """Returns either:
                    {'up': [done, total],
                     'down': [done, total]}
                or:
                    1 for finished
        """
        done = True  # but we'll check for alive threads and set False
        if self.uploader is None:
            up = [0, 0]
        else:
            if self.uploader.isAlive():
                done = False
            up = [self.uploader.finished_size,
                  self.uploader.queue_size]

        if self.downloader is None:
            down = [0, 0]
        else:
            if self.downloader.isAlive():
                done = False
            down = [self.downloader.finished_size,
                    self.downloader.queue_size]

        if not done:  # at least one thread reported being alive
            return {'up': up, 'down': down}
        else:
            return 1


class Node(object):
    """The Node is an abstract class defined by OSF that could be a project
    or a subproject. It can contain files and children (which are themselves
    nodes)

    Nearly all the attributes of this class are read-only. They are set by
    on init based on the OSF database

    Parameters
    ----------

    session : a Session object
    id : str or dict
        This can be the project/node ID in open science framework, in which
        case the info will be fetched for that Node.
        Or it can be the json data for that Node directly (if that has been
        retrieved already)

    """
    def __init__(self, session, id):
        if session is None:
            session = Session()  # create a default (anonymous Session)
        self.session = session
        if type(id) is dict:
            self.json = id
            id = self.json['id']
        elif id.startswith('http'):
            # treat as URL. Extract the id from the request data
            reply = self.session.get(id, timeout=10.0)
            if reply.status_code == 200:
                self.json = reply.json()['data']
                id = self.json['id']
            elif reply.status_code == 410:
                raise exceptions.OSFDeleted(
                    "OSF Project {} appears to have been deleted"
                    .format(id))
            else:
                raise exceptions.HTTPSError(
                    "Failed to fetch OSF Project with URL:\n{}"
                    .format(reply, id))
        else:
            # treat as OSF id and fetch the URL
            url = "{}/nodes/{}/".format(constants.API_BASE, id)
            reply = self.session.get(url, timeout=10.0)
            if reply.status_code == 200:
                self.json = reply.json()['data']
            elif reply.status_code == 410:
                raise exceptions.OSFDeleted(
                    "OSF Project {} appears to have been deleted"
                    .format(url))
            else:
                raise exceptions.HTTPSError(
                    "Failed to fetch OSF Project with ID:\n {}: {}\n"
                    .format(reply, url))
        # also get info about files if possible
        files_reply = self.session.get("{}/nodes/{}/files"
                                       .format(constants.API_BASE, id),
                                       timeout=10.0)
        if files_reply.status_code == 200:
            for provider in files_reply.json()['data']:
                if provider['attributes']['name'] == 'osfstorage':
                    self.json['links'].update(provider['links'])
        self.id = id

    def __repr__(self):
        return "Node(%r)" % (self.id)

    def __str__(self):
        return json.dumps(self.json, sort_keys=True, indent=4)

    @property
    def title(self):
        """The title of this node/project
        """
        if "title" in self.json['attributes']:
            return self.json['attributes']['title']
        else:
            return self.json['attributes']['name']

    @property
    def kind(self):
        """Kind of object ('file' or 'folder')
        """
        return 'node'

    @property
    def attributes(self):
        """The attribute (meta)data about this node
        """
        return self.json['attributes']

    @property
    def links(self):
        """The links are the URLs the node has to download, upload etc
        """
        return self.json['links']

    @property
    def children(self):
        """(read only) A list of nodes, one for each child
        """
        child_list = []
        if "children" in self.json['relationships']:
            req = self.session.get("{}/nodes/{}/children"
                                   .format(constants.API_BASE, self.id),
                                   timeout=10.0)
            for node in req.json()['data']:
                child_list.append(Node(session=self.session, id=node["id"]))
        return child_list

    @property
    def parent(self):
        """Returns a new Node of the parent object or None
        """
        parent_URL = None  # unless we can find one somewhere!
        relations = self.json['relationships']
        if 'parent' in relations:
            links = relations['parent']['links']
            if 'self' in links:
                parent_URL = links['self']['href']
            elif 'related' in links:
                parent_URL = links['related']['href']

        # not sure if the above is the only reason that the URL could be None
        if parent_URL is None:
            return None
        else:
            return Node(session=self.session, id=parent_URL)

    def _node_file_list(self, url=None):
        """Returns all the files within a node (including sub-folders)
        """
        if url is None:  # use the root of this Node id
            url = "{}/nodes/{}/files/osfstorage".format(constants.API_BASE,
                                                        self.id)
        reply = self.session.get(url, timeout=10.0).json()['data']
        file_list = []
        for entry in reply:
            f = FileNode(self.session, entry)
            d = f.as_asset()
            # if folder then get the assets below as well
            if f.kind == 'folder':
                logging.info("folderHasPath: {}".format(f.path))
                folder_url = f.links['move']
                file_list.extend(self._node_file_list(folder_url))
            # for folder of files store this asset
            if f.path not in ['', '/']:
                file_list.append(d)
        return file_list

    def create_index(self):
        """Returns a flat list of all files from this node down
        """
        file_list = []
        # process child nodes first
        [file_list.extend(this_child.create_index())
            for this_child in self.children]
        # then process this Node
        file_list.extend(self._node_file_list("{}/nodes/{}/files/osfstorage"
                         .format(constants.API_BASE, self.id)))
        return file_list

    def as_asset(self):
        """Returns a dict containing a subset of the fields that we use to
        store asset info in our indices
        """
        d = {}
        d['id'] = self.id
        d['kind'] = self.kind
        d['path'] = self.path
        d['name'] = self.name
        d['links'] = self.links
        if self.kind == 'file':  # not folder
            d['url'] = self.links['download']
            d['md5'] = self.md5
            d['sha256'] = self.sha256
            d['size'] = self.size
            d['date_modified'] = self.modified
        return d


class FileNode(Node):
    """A Python object to handle file nodes in the OSF database
    This is sufficiently different in its attribtues from normal nodes
    that it shouldn't inherit.

    Parameters
    ----------

    session : a Session object
        Used to retrieve certain attributes
    json_data : a dict-type object
        Storing the fields from an OSF File Node

    """
    def __init__(self, session, id):
        """Initialise with the request(url).json()['data']
        """
        Node.__init__(self, session, id)
        self.id = id

    @property
    def name(self):
        """Name of this file
        """
        return self.json['attributes']['name']

    @property
    def kind(self):
        """Kind of object ('file' or 'folder')
        """
        return self.json['attributes']['kind']

    @property
    def path(self):
        """The path to this folder/file from the root
        """
        if 'materialized' in self.json['attributes'].keys():
            p = self.json['attributes']['materialized'][1:]  # ignore "/"
        else:
            p = self.json['attributes']['name']
        if p.endswith("/"):
            p = p[:-1]
        return p

    @property
    def modified(self):
        if 'modified' in self.json['attributes'].keys():
            return self.json['attributes']['modified']
        else:
            return self.json['attributes']['date_modified']

    @property
    def files(self):
        """A json representation of files at this level of the heirarchy
        """
        if 'files' in self.json:
            return self.json['files']  # exists for top-level nodes
        else:
            return []  # doesn't exist for FileNodes

    @property
    def info(self):
        infoLink = self.links['info']
        reply = self.session.get(infoLink, timeout=10.0)
        return reply.json()['data']

    @property
    def size(self):
        """Only valid for files (returns None for folders)
        """
        if self.kind == "file":
            return self.json['attributes']['size']
        else:
            return None

    @property
    def md5(self):
        if self.kind == "file":
            return self.json['attributes']['extra']['hashes']['md5']
        else:
            return None

    @property
    def sha256(self):
        if self.kind == "file":
            return self.json['attributes']['extra']['hashes']['sha256']
        else:
            return None

    @property
    def sha(self):
        if self.kind == "file":
            return self.json['attributes']['extra']['hashes'][constants.SHA]
        else:
            return None

    def download(self, target_path, threaded=False):
        """Download this file to the target folder

        Parameters
        ----------
        target_folder : str
            The root location to save the files in

        """
        if self.kind != "file":
            raise exceptions.OSFError(
                "pyosf: Attempted to download object of kind={!r} "
                "but download is only possible for files"
                .format(self.kind))
        url = self.links['download']
        self.session.download_file(url=url, local_path=target_path,
                                   threaded=threaded)


class OSFProject(Node):
    """A project Node from the OSF. Most methods are defined by Node

    Parameters
    ----------

    session : a Session object
    id : the id of the project node on OSF

    """
    def __init__(self, session, id):
        Node.__init__(self, session, id)
        self.containers = {}  # a dict of Nodes and folders to contain files
        self.path = ""  # provided for consistency with FileNode
        self.name = ""  # provided for consistency with FileNode
        self._index = None
        self.uploader = None  # to cache asynchronous uploads
        self.downloader = None  # to cache asynchronous downloads

    def __repr__(self):
        return "OSF_Project(%r)" % (self.id)

    @property
    def index(self):
        if self._index is None:
            self.rebuild_index()
        return self._index

    def index_dict(self):
        return dict_from_list(self.index)

    def rebuild_index(self):
        """Returns a flat list of all files from this node down
        """
        file_list = Node.create_index(self)  # Node does the main leg work
        # for Project, find all folders and add them to their own index
        self.containers = {}
        for entry in file_list:
            if entry['kind'] == 'folder':
                self.containers[entry['path']] = entry
        # now we can give containers 'modified dates' based on contents
        for path, entry in self.containers.items():
            modified = '0'
            for asset in file_list:
                if asset['path'].startswith(path):
                    if 'date_modified' in asset and \
                            asset['date_modified'] > modified:
                        modified = asset['date_modified']
            entry['date_modified'] = modified
        self._index = file_list

    def add_container(self, path, kind='folder', changes=None):
        """Adds a container (currently only a folder) recursively.

        If the previous container was a folder or node it doesn't matter; they
        are treated equivalently here.
        """
        if len(self.containers) == 0:
            self.create_index()
        # TODO: what if a node and a folder have the same name?
        if path in self.containers:
            return self.containers[path]  # nothing to do, return the container

        if path == "":
            asset = self.as_asset()
        else:
            outer_path, name = os.path.split(path)
            if outer_path == "":  # we reached the root of the node
                url_create = self.links['new_folder']
                logging.info("Use root container for: {}"
                             .format(path))
            elif outer_path not in self.containers:
                logging.info("Needing new folder: {}".format(outer_path))
                container = self.add_container(outer_path)
                logging.info("Basing it in {}".format(container))
                url_create = container['links']['new_folder']
            else:
                container = self.containers[outer_path]
                url_create = container['links']['new_folder']
                logging.info("Using existing {}".format(outer_path))

            url = "{}&name={}".format(url_create, name)
            reply = self.session.put(url, timeout=10.0)
            if reply.status_code == 409:
                # conflict code indicating the folder does exist
                errStr = ("Err409: {}\n"
                          " Tried URL: {}\n"
                          " Current containers: {}\n"
                          " Links: {}"
                          .format(path, url,
                                  self.containers, self.links))
                raise exceptions.OSFError(errStr)
            elif reply.status_code not in [200, 201]:  # some other problem
                raise exceptions.HTTPSError(
                    "URL:{}\nreply:{}"
                    .format(url, json.dumps(reply.json(), indent=2)))
            else:
                reply_json = reply.json()['data']
            asset = FileNode(self.session, reply_json).as_asset()
            logging.info("Created remote {} with path={}"
                         .format(asset['kind'], asset['path']))
            if changes:
                changes.add_to_index(asset['path'])
        self.containers[path] = asset
        return asset

    def find_asset(self, path):
        """Finds an asset (including id and links) by its path
        """
        return find_by_key(self.index, 'path', path)

    def add_file(self, asset, update=False, new_path=None,
                threaded=False, changes=None):
        """Adds the file to the OSF project.
        If containing folder doesn't exist then it will be created recursively
        update is used if the file already exists but needs updating (version
        will be incremented).
        """
        # get the url and local path
        local_path = asset['full_path']
        if new_path is None:
            new_path = asset['path']
        if update:
            url_upload = asset['links']['upload']
            logging.info("Updating file : {}".format(asset['path']))
        else:
            container, name = os.path.split(new_path)
            folder_asset = self.add_container(container)
            url_upload = folder_asset['links']['upload']
            if not url_upload.endswith("?kind=file"):
                url_upload += "?kind=file"
            url_upload += "&name={}".format(name)
            # do the upload
            logging.info("Uploading file {} to container:{}"
                         .format(name, folder_asset['path']))
        if 'size' in asset:
            size = asset['size']
        else:
            size = 0
        self.session.upload_file(url=url_upload, local_path=local_path,
                                 size=size, threaded=threaded, changes=changes)

    def rename_file(self, asset, new_path, changes=None):
        # ensure the target location exists
        new_folder, new_name = os.path.split(new_path)
        # get the url and perform the move
        url_move = asset['links']['move']
        # there's actually a more complicated version allowing a *move*
        # (change of location) but we're just using rename
        body = """{"action":   "rename",
                "rename":   "%s"}
               """ % (new_name)
        reply = self.session.post(url_move, data=body, timeout=30.0)
        if reply.status_code not in [200, 201]:
            raise exceptions.HTTPSError(
                "Failed remote file move URL:{}\nreply:{}"
                .format(url_move, json.dumps(reply.json(), indent=2)))
        if changes:
            changes.rename_in_index(asset, new_path)

    def del_file(self, asset, changes=None):
        url_del = asset['links']['delete']
        reply = self.session.delete(url_del)
        if reply.status_code != 204:
            raise exceptions.HTTPSError(
                "Failed remote file delete URL:{}\nreply:{}"
                .format(url_del, json.dumps(reply.json(), indent=2)))
        if asset['path'] in self.containers:
            del self.containers[asset['path']]
        if changes:
            changes.remove_from_index(asset['path'])

if __name__ == "__main__":
    import pytest
    this_folder, filename = os.path.split(constants.__file__)
    pytest.main(["tests/test_project.py", "-s"])
