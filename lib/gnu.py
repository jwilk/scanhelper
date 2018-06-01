# encoding=UTF-8

# Copyright © 2011-2018 Jakub Wilk <jwilk@jwilk.net>
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

'''direct access to some functions from GNU libc'''

import ctypes

libc = ctypes.CDLL(None)

def sprintf(fmt, *args):
    string = ctypes.c_char_p()
    libc.asprintf(ctypes.byref(string), fmt, *args)
    try:
        return string.value
    finally:
        libc.free(string)

__all__ = ['sprintf']

# vim:ts=4 sts=4 sw=4 et
