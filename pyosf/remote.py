
"""Classes and functions to access remote (https://OSF.io) projects
"""

# License info: the code for Session.authenticate() is derived from the code
# in https://github.com/CenterForOpenScience/osf-sync/blob/develop/osfoffline/utils/authentication.py

import constants
import os
import time
import requests
import json
import datetime
try:
    from psychopy import logging
except:
    import logging


class AuthError(Exception):
    """Authentication error while connecting to the OSF"""
    pass


class Session(requests.Session):
    """A class to track a session with the OSF server.

    The session will store a token, which can then be used to authenticate
    for project read/write access
    """
    def __init__(self, username=None, password=None, token=None, otp=None):
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
        # set token (which will update session headers as needed)
        if token is not None:
            self.token = token
        elif username is not None:
            self.token = self.authenticate(username, password, otp)
        self.headers.update({'content-type': 'application/json'})

    def find_users(self, searchStr):
        """Find user IDs whose name matches a given search string
        """
        reply = self.get(constants.API_BASE + "/users/?filter[full_name]=%s"
                         % (searchStr)).json()
        users = []
        for thisUser in reply['data']:
            attrs = thisUser['attributes']
            attrs['id'] = thisUser['id']
            users.append(attrs)
        return users

    def find_user_projects(self, user_id):
        """Finds all the projects of a given userID
        """
        reply = self.get(constants.API_BASE +
            "/users/%s/nodes?filter[category]=project" % user_id).json()
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
    def token(self, token):
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
        json_resp = resp.json()
        data = json_resp['data']
        self.user_id = data['id']
        self.user_full_name = data['attributes']['full_name']

    def authenticate(self, username, password, otp=None):
        """Provide the username and

        This authentication code comes from the
        """
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
                raise AuthError('Must provide code for two-factor authentication')
            else:
                raise AuthError('Invalid credentials')
        elif not resp.status_code == 201:
            raise AuthError('Invalid authorization response')
        else:
            json_resp = resp.json()
            return json_resp['data']['attributes']['token_id']


class Node(object):
    """The Node is an abstract class defined by OSF that could be a project
    or a subproject. It can contain files and children (which are themselves
    nodes)

    Nearly all the attributes of this class are read-only. They are set by
    on init based on the OSF database
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
            req = self.session.get("{}/nodes/{}/".format(constants.API_BASE,id))
            self.json = req.json()['data']

    def __repr__(self):
        return "Node(%r)" %(self.id)

    def __str__(self):
        return json.dumps(self.json, sort_keys=True, indent=4)

    @property
    def id(self):
        """The unique identifier of this node/project for the OSF database
        """
        return self.json['id']

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
            print('thisFolderEntry', entry['type'], entry['id'])
            f = FileNode(self.session, entry)
            d = {}
            d['type'] = f.kind
            d['path'] = f.path
            if f.kind == 'file':  # not folder
                d['url'] = f.links['download']
                d['md5'] = f.md5
                d['bytes'] = f.size
                d['date_modified'] = f.modified
                file_list.append(d)
            elif f.kind == 'folder':
                folder_url = f.links['move']
                file_list.extend(self._node_file_list(folder_url))
        return file_list

    def create_index(self):
        """Returns a flat list of all files in the tree from this node downwards
        """
        file_list = []
        # process child nodes first
        [file_list.extend(this_child.create_index())
            for this_child in self.children]

        file_list.extend(self._node_file_list("{}/nodes/{}/files/osfstorage"
                         .format(constants.API_BASE, self.id)))
        # then process our own files
#        req = self.session.get(constants.API_BASE+"/nodes/{}/files/osfstorage"\
#            .format(self.id))
#        for entry in req.json()['data']:
#            f = FileNode(self.session, entry)
#            d = {}
#            print "thisFileIs", f.name, f.path
#            d['type'] = f.kind
#            d['path'] = f.path
#            d['date_modified'] = f.attributes['date_modified']
#            elif f.kind == 'folder':
#                filesUrl = f.links['move'] #this is a bug in API V2? should be info link
#                file_list.extend(self._folder_file_list(filesUrl))

#                reply = self.session.get(filesUrl).json()['data']
#                print self.session.headers
#                print reply
#                for entry in reply:
#                    print 'thisFolderEntry', entry['type'], entry['id']
#                    folder_files = Node(session=self.session, id=entry['id'], ).create_index()
#                    file_list.extend(folder_files)

        return file_list

class FileNode(object):
    """A Python object to handle file nodes in the OSF database
    This is sufficiently different in its attribtues from normal nodes
    that it shouldn't inherit.
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
            return self.json['attributes']['materialized']
        else:
            return self.json['attributes']['path']

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
        if self.kind=="file":
            return self.json['attributes']['size']
        else:
            return None

    @property
    def md5(self):
        if self.kind=="file":
            return self.json['attributes']['extra']['hashes']['md5']
        else:
            return None

    @property
    def attributes(self):
        return self.json['attributes']

    def download(self, target_folder):
        """Download this file to the target folder
        """
        URL = self.links['download']
        r = self.session.get(URL, stream=True)
        file_path = os.path.join(target_folder, self.name)
        if r.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)

class Project(Node):
    """Top level node
    (currently this does nothing different to Node)
    """
    def __init__(self, session, id):
        Node.__init__(self, session, id)
    def __repr__(self):
        return "Project(%r)" %(self.id)
    def downloadAll(self, local_path=None):
        for file_node in self.file_list:
            file_node.download(target_folder = local_path)
            print '.',

#print("** Finding PsychoPy projects**")
#psychopyProjs = self.session.get(constants.API_BASE+"/nodes/?filter[tags]=coder")
#for node in psychopyProjs.json()['data']:
#    print(node['attributes']['title'])
#    print("  " + node['links']['html'])

def test_searchUser(session, name = 'peirce', printing=False):
    if printing:
        print("\n** Finding Jon **")
    users = session.find_users(name)
    full_name = users[0]['full_name']
    print users[0]
    user_id = users[0]['id']
    if printing:
        print "Found OSF user '%s' with id=%s" %(full_name, user_id)

def test_search_projects(session, user_id, printing=False):
    if printing:
        print("\n** Finding Jon Projects **")
    jonProjs = session.find_user_projects(user_id)
    for proj in jonProjs:
        if printing:
            print(proj['title'])

def test_file_listing(session, proj_id, printing=False):
    if printing:
        print("\n** Finding Files **")
    proj = Project(id=proj_id, session=session)
    if printing:
        print repr(proj), proj.title, "nodes:"
    #print proj
    for this_child in proj.children:
        if printing:
            print ' %r (%r), parent=%r' %(this_child.title,
                this_child, this_child.parent)
    #look at some file objects for proj
#    print repr(proj), proj.title, "files:"
    print json.dumps(proj.create_index(), indent=2)
#        print ' - ', this_file.name, this_file.kind, this_file.size, this_file.path
#        print "  info:", this_file.links['info']
#        if this_file.kind == 'file': #not folder
#            print "  download:", this_file.links['download']

if __name__ == "__main__":

    session = Session(username='jon@peirce.org.uk', password='aTestPassword')
    print "{}: {}".format(session.user_id, repr(session.user_full_name))

    test_searchUser(session, 'peirce', printing=True)

    t0 = time.time()
    test_search_projects(session, user_id='tkedn', printing=True)
    print "took {:.4f}s".format(time.time()-t0)

    projs = session.find_my_projects()
    proj_id = projs[1]['id']
    t0 = time.time()
    test_file_listing(proj_id=proj_id, session=session)
    print "took %.4fs" %(time.time()-t0)