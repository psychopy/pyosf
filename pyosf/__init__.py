__version__ = '1.0.0'
__license__ = 'MIT'
__author__ = 'Jonathan Peirce'
__author_email__ = 'jon@peirce.org.uk'
__maintainer_email__ = 'jon@peirce.org.uk'
__url__ = 'https://github.com/psychopy/pyosf'
__downloadUrl__ = 'https://github.com/psychopy/pyosf/releases/'

from .remote import Session, TokenStorage, AuthError, HTTPSError
from .project import Project
from . import constants
import os

# create a logfile for this session
logfile_path = os.path.join(constants.PYOSF_FOLDER, 'last_session.log')
try:
    from psychopy import logging
    logfile = logging.LogFile(logfile_path, level=logging.DEBUG)
except ImportError:
    import logging
    logfile = logging.FileHandler(logfile_path, mode='w')
