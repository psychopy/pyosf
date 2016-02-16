# -*- coding: utf-8 -*-
"""
Part of the pyosf package
https://github.com/psychopy/pyosf/

Released under MIT license

@author: Jon Peirce
"""

from __future__ import absolute_import, print_function


def find_by_key(in_list, key, val):
    """Returns the first item with key matching val
    """
    return next(item for item in in_list if item[key] == val)


def dict_from_list(in_list, key):
    """From a list of dicts creates a dict of dicts using a given key name
    """
    d = {}
    for entry in in_list:
        d[entry[key]] = entry
    return d
