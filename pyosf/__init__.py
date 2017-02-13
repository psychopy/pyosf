__version__ = '1.0.5'
__license__ = 'MIT'
__author__ = 'Jonathan Peirce'
__author_email__ = 'jon@peirce.org.uk'
__maintainer_email__ = 'jon@peirce.org.uk'
__url__ = 'https://github.com/psychopy/pyosf'
__downloadUrl__ = 'https://github.com/psychopy/pyosf/releases/'

from .remote import Session, TokenStorage
from .exceptions import AuthError, HTTPSError, OSFError, OSFDeleted
from .project import Project
from . import constants
import os

# create a logfile for this session
logfile_path = os.path.join(constants.PYOSF_FOLDER, 'last_session.log')
if not os.path.isdir(constants.PYOSF_FOLDER):
    os.makedirs(constants.PYOSF_FOLDER)
# prefer psychopy logging but use built-in logging if not available
try:
    from psychopy import logging
    logfile = logging.LogFile(logfile_path, level=logging.DEBUG)
except ImportError:
    import logging
    logfile = logging.FileHandler(logfile_path, mode='w')
