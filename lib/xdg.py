# encoding=UTF-8

# Copyright © 2012-2015 Jakub Wilk <jwilk@jwilk.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 dated June, 1991.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.

'''
tiny replacement for PyXDG's xdg.BaseDirectory
'''

import os

xdg_config_home = os.environ.get('XDG_CONFIG_HOME') or ''
if not os.path.isabs(xdg_config_home):
    xdg_config_home = os.path.join(os.path.expanduser('~'), '.config')

xdg_config_dirs = os.environ.get('XDG_CONFIG_DIRS') or '/etc/xdg'
xdg_config_dirs = (
    [xdg_config_home] +
    filter(os.path.abspath, xdg_config_dirs.split(os.path.pathsep))
)

def save_config_path(resource):
    path = os.path.join(xdg_config_home, resource)
    try:
        os.makedirs(path, 0o700)
    except OSError:
        if not os.path.isdir(path):
            raise
    return path

def load_config_paths(resource):
    for config_dir in xdg_config_dirs:
        path = os.path.join(config_dir, resource)
        if os.path.exists(path):
            yield path

# vim:ts=4 sts=4 sw=4 et
