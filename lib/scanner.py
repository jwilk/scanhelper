# encoding=UTF-8

# Copyright © 2011-2022 Jakub Wilk <jwilk@jwilk.net>
#
# This file is part of scanhelper.
#
# scanhelper is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 as published
# by the Free Software Foundation.
#
# scanhelper is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.

'''scanner support'''

import distutils.version

from . import utils

try:
    import _sane as sane
except ImportError as ex:
    utils.enhance_import_error(ex, 'Python SANE', 'python3-sane', 'https://pypi.org/project/python-sane/')
    raise

_version = None

def initialize():
    global _version
    if _version:
        return
    _version = sane.init()

def get_sane_version():
    initialize()
    version = str.join('.', map(str, _version[1:]))
    return distutils.version.LooseVersion(version)

def get_devices():
    initialize()
    return sane.get_devices()

class OptionDescriptor:

    def __init__(self, index, type_, unit, size, capabilities, constraint):
        self.index = index
        self.type_ = type_
        self.unit = unit
        self.size = size
        self.capabilities = capabilities
        self.constraint = constraint

class Device:

    def __init__(self, name, vendor, model, type_):
        self.name = name
        self.vendor = vendor
        self.model = model
        self.type_ = type_
        self._device = None
        self.open()
        assert self._device is not None
        self._init_options()

    def _init_options(self):
        self._options = {}
        for index, name, title, desc, type_, unit, size, capabilities, constraint in self._device.get_options():
            del title, desc
            if name is None:
                continue
            if name == 'button' or (capabilities & sane.CAP_HARD_SELECT):
                self._options[name] = OptionDescriptor(index, type_, unit, size, capabilities, constraint)

    def __iter__(self):
        return iter(self._options)

    def __getitem__(self, name):
        self.open()
        index = self._options[name].index
        assert self._device is not None
        return self._device.get_option(index)

    def open(self):
        if self._device is not None:
            return
        self._device = sane._open(self.name)  # pylint: disable=protected-access

    def close(self):
        if self._device is None:
            return
        self._device.close()
        self._device = None

# SANE_STATUS_* constants
# =======================

class Status:
    GOOD = 0
    UNSUPPORTED = 1
    CANCELLED = 2
    DEVICE_BUSY = 3
    INVAL = 4
    EOF = 5
    JAMMED = 6
    NO_DOCS = 7
    COVER_OPEN = 8
    IO_ERROR = 9
    NO_MEM = 10
    ACCESS_DENIED = 11

__all__ = [
    'Device',
    'Status',
    'get_devices',
    'get_sane_version',
    'initialize',
]

# vim:ts=4 sts=4 sw=4 et
