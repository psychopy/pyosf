
"""Classes and functions to access remote (https://OSF.io) projects
"""

# License info: the code for Session.authenticate() is derived from the code
# in https://github.com/CenterForOpenScience/osf-sync/blob/develop/...
#    /osfoffline/utils/authentication.py

from __future__ import absolute_import, print_function
import os
import sys
import requests
import json
import datetime
try:
    from psychopy import logging
    console = logging.console
except:
    import logging
    console = logging.getLogger()
from . import constants

PY3 = sys.version_info > (3,)


class AuthError(Exception):
    """Authentication error while connecting to the OSF"""
    pass


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
            if PY3:
                f.write(bytes(json_str, 'UTF-8'))
            else:
                f.write(json_str)


class Session(requests.Session):
    """A class to track a session with the OSF server.

    The session will store a token, which can then be used to authenticate
    for project read/write access
    """
    def __init__(self, username=None, password=None, token=None, otp=None,
                 remember_me=True):
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

    def open_project(self, proj_id):
        """Returns a OSF_Project object or None (if that id couldn't be opened)
        """
        try:
            return OSFProject(session=self, id=proj_id)
        except:
            return None

    def search_project_names(self, search_str, tags="psychopy"):
        """
        """
        psychopyProjs = self.session.get("{}/nodes/?filter[tags]=coder"
                                         .format(constants.API_BASE))

        return psychopyProjs.json()

    def find_users(self, search_str):
        """Find user IDs whose name matches a given search string
        """
        reply = self.get("{}/users/?filter[full_name]={}"
                         .format(constants.API_BASE, search_str)).json()
        users = []
        for thisUser in reply['data']:
            attrs = thisUser['attributes']
            attrs['id'] = thisUser['id']
            users.append(attrs)
        return users

    def find_user_projects(self, user_id=None):
        """Finds all the projects of a given user_id (None for current user)
        """
        if user_id is None:
            user_id = self.user_id
        reply = self.get("{}/users/{}/nodes?filter[category]=project"
                         .format(constants.API_BASE, user_id)).json()
        projs = []
        for thisProj in reply['data']:
            attrs = thisProj['attributes']
            attrs['id'] = thisProj['id']
            projs.append(attrs)
        return projs

    def find_my_projects(self):
        """Find project IDs matching a given search string, that the
        current authenticaed user/session can access
        """
        # NB user_id was created during self.authenticate()
        return self.find_user_projects(self.user_id)

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
        resp = self.get(constants.API_BASE+"/users/me/")
        if resp.status_code != 200:
            raise AuthError('Invalid credentials trying to fetch user data.')
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
            except AuthError:
                if password is None:
                    raise AuthError("User token didn't work and no password "
                                    "has been provided")
        elif password is None:
            raise AuthError("No auth token found and no password given")
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
            auth=(username, password)
            )
        if resp.status_code in (401, 403):
            # If login failed because of a missing two-factor authentication
            # code, notify the user to try again
            # This header appears for basic auth requests, and only when a
            # valid password is provided
            otp_val = resp.headers.get('X-OSF-OTP', '')
            if otp_val.startswith('required'):
                raise AuthError('Must provide code for two-factor'
                                'authentication')
            else:
                raise AuthError('Invalid credentials')
        elif not resp.status_code == 201:
            raise AuthError('Invalid authorization response')
        else:
            json_resp = resp.json()
            logging.info("Successfully authenticated with username/password")
            self.authenticated = True
            self.token = json_resp['data']['attributes']['token_id']
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
    id : the project/node id in open science framework

    """
    def __init__(self, session, id):
        if session is None:
            session = Session()  # create a default (anonymous Session)
        self.session = session
        if id.startswith('http'):
            # treat as URL. Extract the id from the request data
            req = self.session.get(id)
            self.json = req.json()['data']
        else:
            # treat as OSF id and fetch the URL
            req = self.session.get("{}/nodes/{}/".format(constants.API_BASE,
                                   id))
            self.json = req.json()['data']
        self.id = id

    def __repr__(self):
        return "Node(%r)" % (self.id)

    def __str__(self):
        return json.dumps(self.json, sort_keys=True, indent=4)

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
    def title(self):
        """The title of this node/project
        """
        return self.json['attributes']['title']

    @property
    def children(self):
        """(read only) A list of nodes, one for each child
        """
        req = self.session.get("{}/nodes/{}/children"
                               .format(constants.API_BASE, self.id))

        child_list = []
        for node in req.json()['data']:
            child_list.append(Node(node["id"]))
        return child_list

    @property
    def parent(self):
        """Returns a new Node of the parent object or None
        """
        links = self.json['relationships']['parent']['links']
        if 'self' in links:
            parent_URL = links['self']['href']
        elif 'related' in links:
            parent_URL = links['related']['href']
        else:
            parent_URL = None
        # not sure if the above is the only reason that the URL could be None
        if parent_URL is None:
            return None
        else:
            return Node(parent_URL)

    def _node_file_list(self, url):
        """Returns all the files within a node (including sub-folders)
        """
        reply = self.session.get(url).json()['data']
        file_list = []
        for entry in reply:
            f = FileNode(self.session, entry)
            d = {}
            d['kind'] = f.kind
            d['path'] = f.path
            d['name'] = f.name
            d['links'] = f.links
            if f.kind == 'file':  # not folder
                d['url'] = f.links['download']
                d['md5'] = f.md5
                d['sha256'] = f.sha256
                d['size'] = f.size
                d['date_modified'] = f.modified
                file_list.append(d)
            elif f.kind == 'folder':
                folder_url = f.links['move']
                file_list.extend(self._node_file_list(folder_url))
        return file_list

    def create_index(self):
        """Returns a flat list of all files from this node down
        """
        file_list = []
        # process child nodes first
        [file_list.extend(this_child.create_index())
            for this_child in self.children]

        file_list.extend(self._node_file_list("{}/nodes/{}/files/osfstorage"
                         .format(constants.API_BASE, self.id)))

        return file_list


class FileNode(object):
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
    def __init__(self, session, json_data):
        """Initialise with the request(url).json()['data']
        """
        self.session = session
        self.json = json_data

    @property
    def name(self):
        """Name of this file
        """
        return self.json['attributes']['name']

    @property
    def id(self):
        """Unique identifier in OSF
        """
        return self.json['id']

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
            return self.json['attributes']['materialized'][1:]  # ignore "/"
        else:
            return self.json['attributes']['name']

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
        return self.json['files']

    @property
    def links(self):
        """The links are the URLs the node has to download, upload etc
        """
        return self.json['links']

    @property
    def info(self):
        infoLink = self.links['info']
        reply = self.session.get(infoLink)
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
    def attributes(self):
        return self.json['attributes']

    def download(self, target_folder):
        """Download this file to the target folder

        Parameters
        ----------
        target_folder : str
            The root location to save the files in

        """
        URL = self.links['download']
        r = self.session.get(URL, stream=True)
        file_path = os.path.join(target_folder, self.name)
        if r.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)


class OSFProject(Node):
    """A project Node from the OSF. Most methods are defined by Node

    Parameters
    ----------

    session : a Session object
    id : the id of the project node on OSF

    """
    def __init__(self, session, id):
        Node.__init__(self, session, id)

    def __repr__(self):
        return "OSF_Project(%r)" % (self.id)

    def downloadAll(self, local_path=None):
        for file_node in self.file_list:
            file_node.download(target_folder=local_path)


if __name__ == "__main__":
    # set up logging to give more info
    console.setLevel(logging.DEBUG)
    # set up session with full info
    tokens = TokenStorage()
    if 'jon@peirce.org.uk' in tokens:
        del tokens['jon@peirce.org.uk']
        tokens.save()
    session = Session(username='jon@peirce.org.uk', password='aTestPassword')
    print("Success with username and password")
    # should now be able to use username only
    session = Session(username='jon@peirce.org.uk')
    print("Success with username only (stored token)")

    if hasattr(logging, 'flush'):
        logging.flush()  # psychopy.logging needs manual flush
