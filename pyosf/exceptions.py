# -*- coding: utf-8 -*-
"""Classes and functions to access remote (https://OSF.io) projects

Part of the pyosf package
https://github.com/psychopy/pyosf/

Released under MIT license

Created on Sun Feb  7 21:31:15 2016

@author: lpzjwp
"""

class AuthError(Exception):
    """Authentication error while connecting to the OSF"""
    pass


class HTTPSError(Exception):
    """Error connecting to web resource
    """
    pass


class OSFError(Exception):
    """Errors accessing OSF files (e.g. no such user)
    """
    pass


class OSFDeleted(Exception):
    """The resource (e.g. Project) has been deleted
    """
    pass
    

class CancelledError(Exception):
    """Detect when a file upload is cancelled
    """
    pass