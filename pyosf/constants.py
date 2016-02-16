# -*- coding: utf-8 -*-
"""
Created on Mon Feb  1 18:56:01 2016

@author: jon.peirce@gmail.com
"""

API_BASE = 'https://api.osf.io/v2'

PROJECT_NAME = 'pyosf'
APPLICATION_SCOPES = 'osf.full_write'

from os import path
home = path.expanduser("~")
PYOSF_FOLDER = path.join(home, '.pyosf')

SHA = "md5"  # could switch to "sha256"

import sys
PY3 = sys.version_info > (3,)
