
from setuptools import setup, find_packages
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.md')) as f:
    long_description = f.read()

from pyosf import __version__

setup(
    name='pyosf',
    version=__version__,
    description='Python lib for synching with OpenScienceFramework projects',
    long_description=long_description,
    url='https://github.com/psychopy/pyosf',
    author='Jon Peirce',
    author_email='jon.peirce@gmail.com',
    license='MIT',
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',          
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX',
    ],
    keywords='Open Science Framework PsychoPy',
    packages=find_packages(exclude=['docs', 'tests']),
    # $ pip install -e .[dev,test]
    setup_requires=['pytest-runner', 'requests'],
    tests_require=['pytest', 'coverage', 'requests'],
    package_data={
        'sample': ['package_data.dat'],
    },
)
