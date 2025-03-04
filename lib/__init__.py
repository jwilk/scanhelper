# encoding=UTF-8

# Copyright © 2011-2024 Jakub Wilk <jwilk@jwilk.net>
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

'''
scanhelper's private modules
'''

import sys

if sys.version_info < (2, 7):
    raise RuntimeError('Python 2.7 is required')
if sys.version_info >= (3, 0):
    raise RuntimeError('Python 2.X is required')

__version__ = '0.8'

# vim:ts=4 sts=4 sw=4 et
