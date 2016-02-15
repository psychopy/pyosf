# -*- coding: utf-8 -*-
"""
Created on Mon Feb 15 21:59:47 2016

@author: lpzjwp
"""

def find_by_key(in_list, key, val):
    """Returns the first item with key matching val
    """
    return (item for item in in_list if item[key] == val).next()

def dict_from_list(in_list, key):
    """From a list of dicts creates a dict of dicts using a given key name
    """
    d = {}
    for entry in in_list:
        d[entry[key]] = entry
    return d