# encoding=UTF-8

# Copyright © 2015-2018 Jakub Wilk <jwilk@jwilk.net>
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

import os

from .tools import (
    assert_equal,
)

from lib import __version__

here = os.path.dirname(__file__)
docdir = os.path.join(here, os.pardir, 'doc')

def test_changelog():
    path = os.path.join(docdir, 'changelog')
    with open(path, 'rt') as file:
        line = file.readline()
    changelog_version = line.split()[1].strip('()')
    assert_equal(changelog_version, __version__)

# vim:ts=4 sts=4 sw=4 et
