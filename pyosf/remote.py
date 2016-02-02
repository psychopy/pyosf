
"""Classes and functions to access remote (https://OSF.io) projects
"""

# License info: the code for Session.authenticate() is derived from the code
# in https://github.com/CenterForOpenScience/osf-sync/blob/develop/osfoffline/utils/authentication.py

import constants
import os, time
import requests
import json
import datetime

class AuthError(Exception):
    """Authentication error while connecting to the OSF"""
    pass

def find_user(name):
    """Find a user and retrieve their id and attributes
    """
    reply = requests.get(constants.API_BASE+"/users/?filter[full_name]=%s" %(name)).json()
    attributes = reply['data'][0]['attributes']
    userID = reply['data'][0]['id']
    return userID, attributes

def find_user_projects(userID):
    """Finds all the projects of a given userID
    """
    return requests.get(constants.API_BASE+"/users/%s/nodes?filter[category]=project" %userID).json()

class Session(object):
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
        self.username = username
        self.password = password
        self.user_id = None #populate when token property is set
        self.user_full_name = None
        #create a basic session
        self._session = requests.Session()
        #set token (which will update session headers as needed)
        if token is not None:
            self.token = token
        elif username is not None:
            self.token = self.authenticate(username, password, otp)

    def find_users(self, searchStr):
        """Find user IDs whose name matches a given search string
        """
        reply = self._session.get(constants.API_BASE+"/users/?filter[full_name]=%s"\
            %(searchStr)).json()
        attributes = reply['data'][0]['attributes']
        userID = reply['data'][0]['id']
        return userID, attributes

    def find_my_projects(self, searchStr):
        """Find project IDs matching a given search string, that the
        current authenticaed user/session can access
        """
        userID, name = self.me

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
        self._session.headers.update(headers)
        # then populate self.userID and self.userName
        resp = self._session.get(constants.API_BASE+"/users/me/")
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
        resp = requests.post(
            token_url,
            headers=headers,
            data=json.dumps(token_request_body),
            auth=(username, password)
            )
        if resp.status_code in (401, 403):
            # If login failed because of a missing two-factor authentication code, notify the user to try again
            # This header appears for basic auth requests, and only when a valid password is provided
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
    def __repr__(self):
        return "Node(%r)" %(self.id)
    def __str__(self):
        return json.dumps(self.json, sort_keys=True, indent=4)
    def __init__(self, id):
        if id.startswith('http'):
            #treat as URL. Extract the id from the request data
            req = requests.get(id)
            self.json = req.json()['data']
        else:
            #treat as OSF id and fetch the URL
            req = requests.get("https://api.osf.io/v2/nodes/%s/" %id)
            self.json = req.json()['data']
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
        req = requests.get("https://api.osf.io/v2/nodes/%s/children" %self.id)
        child_list = []
        for node in req.json()['data']:
            child_list.append(Node(node["id"]))
        return child_list
    @property
    def parent(self):
        """Returns a new Node of the parent object or None
        """
        if 'self' in self.json['relationships']['parent']['links']:
            parent_URL = self.json['relationships']['parent']['links']['self']['href']
        elif 'related' in self.json['relationships']['parent']['links']:
            parent_URL = self.json['relationships']['parent']['links']['related']['href']
        else:
            parent_URL = None
        #not sure if the above is the only reason that the URL could be None
        if parent_URL is None:
            return None
        else:
            return Node(parent_URL)
    @property
    def node_file_list(self):
        """Returns the file list at this level only (not including child nodes)
        """
        t0 = time.time()
        req = requests.get("https://api.osf.io/v2/nodes/%s/files/osfstorage" %self.id)
        print("storage req took%.3fs" %(time.time()-t0))
        file_list=[]
        for this_file in req.json()['data']:
            file_list.append(FileNode(this_file))
        return file_list
    @property
    def file_list(self):
        """Returns a flat list of all files in the tree from this node downwards
        """
        file_list = self.node_file_list
        for this_child in self.children:
            print 'x',
            file_list.extend(this_child.file_list)
        return file_list

class FileNode(object):
    """A Python object to handle file nodes in the OSF database
    This is sufficiently different in its attribtues from normal nodes
    that it shouldn't inherit.
    """
    def __init__(self, json_data):
        """Initialise with the request(url).json()['data']
        """
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
        return self.json['attributes']['path']
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
    def size(self):
        """Only valid for files (returns None for folders)
        """
        if self.kind=="file":
            return self.json['attributes']['size']
        else:
            return None
    def download(self, target_folder):
        """Download this file to the target folder
        """
        URL = self.links['download']
        r = requests.get(URL, stream=True)
        file_path = os.path.join(target_folder, self.name)
        if r.status_code == 200:
            with open(file_path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)

class Project(Node):
    """Top level node
    (currently this does nothing different to Node)
    """
    def __init__(self, id, local_path):
        self.local_path = local_path
        Node.__init__(self, id)
    def __repr__(self):
        return "Project(%r)" %(self.id)
    def downloadAll(self, local_path=None):
        for file_node in self.file_list:
            file_node.download(target_folder = local_path)
            print '.',

#print("** Finding PsychoPy projects**")
#psychopyProjs = requests.get(constants.API_BASE+"/nodes/?filter[tags]=coder")
#for node in psychopyProjs.json()['data']:
#    print(node['attributes']['title'])
#    print("  " + node['links']['html'])

def test_searchUser(name = 'peirce', printing=False):
    if printing:
        print("\n** Finding Jon **")
    user_id, attributes = find_user(name)
    full_name = attributes['full_name']
    if printing:
        print "Found OSF user '%s' with id=%s" %(full_name, user_id)

def test_search_projects(user_id, printing=False):
    if printing:
        print("\n** Finding Jon Projects **")
    jonProjs = find_user_projects(user_id)
    for node in jonProjs['data']:
        if printing:
            print(node['attributes']['title'])
            print("  " + node['links']['html'])

def test_file_listing(proj_id, printing=False):
    if printing:
        print("\n** Finding Files **")
    proj = Project(id=proj_id, local_path="~/Downloads/testProj") #Jon's Motion Silencing project
    if printing:
        print repr(proj), proj.title, "nodes:"
    #print proj
    for this_child in proj.children:
        if printing:
            print ' %r (%r), parent=%r' %(this_child.title, this_child, this_child.parent)
    #look at some file objects for proj
    print repr(proj), proj.title, "files:"
    for this_file in proj.file_list:
        print ' - ', this_file.name, this_file.kind, this_file.size, this_file.path
        print "  info:", this_file.links['info']
        if this_file.kind == 'file': #not folder
            print "  download:", this_file.links['download']

if __name__=="__main__":
    test_searchUser('peirce', printing=True)

    t0 = time.time()
    test_search_projects(user_id='tkedn', printing=True)
    print "took %.4fs" %(time.time()-t0)

    session = Session(username='xxxxxx@xxxxxxxxxxx', password='xxxxxxxxxx')
    print session._session.headers
    print "{}: {}".format(session.user_id, repr(session.user_full_name))
#    t0 = time.time()
#    test_file_listing(proj_id='kesjg')
#    print "took %.4fs" %(time.time()-t0)