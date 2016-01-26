"""The main classes to be used by external scripts/apps

These should be imported into the root project __init__.

Standard usage will then be::

    import pyosf
    #create an authenticated session
    session = pyosf.session(username='something', token=someValue)   
    proj_ids = session.find_project_ids(searchStr = 'stroop')
    proj = proj_ids
"""


from . import remote

class Session(object):
    """A class to track a session with the OSF server.
    
    The session will store a token, which can then be used to authenticate
    for project read/write access
    """
    def __init__(self, username=None, password=None, token=None):
        self.username = username
        self.password = password
        self.token = token
        self.current_user_id = None 
    def find_users(self, searchStr):
        """Find user IDs whose name matches a given search string
        """
        reply = requests.get("https://api.osf.io/v2/users/?filter[full_name]=%s"\
            %(name)).json()
        attributes = reply['data'][0]['attributes']
        userID = reply['data'][0]['id']
        return userID, attributes
    def find_my_projects(self, searchStr):
        """Find project IDs matching a given search string, that the
        current authenticaed user/session can access
        """
        pass #todo
        
class Project(Node):
    """Top level node
    (currently this does nothing different to Node)
    """
    def __init__(self, session, id, local_path):
        self.session
        self.local_path = local_path
        remote.Node.__init__(self, id)
    def __repr__(self):
        return "Project(%r)" %(self.id)
    @property
    def tree(self):
        """Return the tree (file/node structure)
        """
        return self.