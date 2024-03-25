# encoding=UTF-8

# Copyright © 2010-2018 Jakub Wilk <jwilk@jwilk.net>
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

import sys

from lib import utils

from .tools import (
    assert_equal,
    assert_raises,
    interim,
)

class test_enhance_import:

    @classmethod
    def setup_class(cls):
        sys.modules['nonexistent'] = None

    def test_debian(self):
        with interim(utils, debian=True):
            with assert_raises(ImportError) as ecm:
                try:
                    import nonexistent
                except ImportError as ex:
                    utils.enhance_import_error(ex,
                        'PyNonexistent',
                        'python-nonexistent',
                        'http://pynonexistent.example.net/'
                    )
                    raise
                nonexistent.f()  # quieten pyflakes
            assert_equal(str(ecm.exception),
                'No module named nonexistent; '
                'please install the python-nonexistent package'
            )

    def test_nondebian(self):
        with interim(utils, debian=False):
            with assert_raises(ImportError) as ecm:
                try:
                    import nonexistent
                except ImportError as ex:
                    utils.enhance_import_error(ex,
                        'PyNonexistent',
                        'python-nonexistent',
                        'http://pynonexistent.example.net/'
                    )
                    raise
                nonexistent.f()  # quieten pyflakes
            assert_equal(str(ecm.exception),
                'No module named nonexistent; '
                'please install the PyNonexistent package <http://pynonexistent.example.net/>'
            )

# vim:ts=4 sts=4 sw=4 et
