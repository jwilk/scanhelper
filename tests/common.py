# encoding=UTF-8

# Copyright © 2010-2015 Jakub Wilk <jwilk@jwilk.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 dated June, 1991.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.

import contextlib
import functools
import os
import re
import sys
import traceback

from nose import SkipTest
from nose.tools import (
    assert_equal,
    assert_true,
)

if sys.version_info >= (2, 7):
    from nose.tools import (
        assert_greater_equal,
        assert_is_instance,
        assert_raises,
        assert_regexp_matches,
    )
else:
    # Python 2.6:
    def assert_greater_equal(x, y):
        assert_true(
            x >= y,
            msg='{0!r} not greater than or equal to {1!r}'.format(x, y)
        )
    def assert_is_instance(obj, cls):
        assert_true(
            isinstance(obj, cls),
            msg='{0!r} is not an instance of {1!r}'.format(obj, cls)
        )
    class assert_raises(object):
        def __init__(self, exc_type):
            self._exc_type = exc_type
            self.exception = None
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_value, tb):
            if exc_type is None:
                assert_true(False, '{0} not raised'.format(elf._exc_type.__name__))
            if not issubclass(exc_type, self._exc_type):
                return False
            self.exception = exc_value
            return True
    def assert_regexp_matches(text, regexp):
        if isinstance(regexp, basestring):
            regexp = re.compile(regexp)
        if not regexp.search(text):
            message = "Regexp didn't match: {0!r} not found in {1!r}".format(regexp.pattern, text)
            assert_true(False, msg=message)

def assert_rfc3339_timestamp(timestamp):
    return assert_regexp_matches(
        timestamp,
        '^[0-9]{4}(-[0-9]{2}){2}T[0-9]{2}(:[0-9]{2}){2}([+-][0-9]{2}:[0-9]{2}|Z)$',
    )

@contextlib.contextmanager
def interim(obj, **override):
    copy = dict((key, getattr(obj, key)) for key in override)
    for key, value in override.iteritems():
        setattr(obj, key, value)
    try:
        yield
    finally:
        for key, value in copy.iteritems():
            setattr(obj, key, value)

@contextlib.contextmanager
def interim_environ(**override):
    keys = set(override)
    copy_keys = keys & set(os.environ)
    copy = dict((key, value) for key, value in os.environ.iteritems() if key in copy_keys)
    for key, value in override.iteritems():
        if value is None:
            try:
                del os.environ[key]
            except KeyError:
                pass
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key in keys:
            try:
                del os.environ[key]
            except KeyError:
                pass
        os.environ.update(copy)

class IsolatedError(Exception):
    pass

def _n_relevant_tb_levels(tb):
    n = 0
    while tb and '__unittest' not in tb.tb_frame.f_globals:
        n += 1
        tb = tb.tb_next
    return n

def fork_isolation(f):

    EXIT_EXCEPTION = 101
    EXIT_SKIP_TEST = 102

    exit = os._exit
    # sys.exit() can't be used here, because nose catches all exceptions,
    # including SystemExit

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        readfd, writefd = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(readfd)
            try:
                f(*args, **kwargs)
            except SkipTest as exc:
                s = str(exc)
                with os.fdopen(writefd, 'wb') as fp:
                    fp.write(s)
                exit(EXIT_SKIP_TEST)
            except Exception:
                exctp, exc, tb = sys.exc_info()
                s = traceback.format_exception(exctp, exc, tb, _n_relevant_tb_levels(tb))
                s = ''.join(s)
                del tb
                with os.fdopen(writefd, 'wb') as fp:
                    fp.write(s)
                exit(EXIT_EXCEPTION)
            exit(0)
        else:
            os.close(writefd)
            with os.fdopen(readfd, 'rb') as fp:
                msg = fp.read()
            msg = msg.rstrip('\n')
            pid, status = os.waitpid(pid, 0)
            if status == (EXIT_EXCEPTION << 8):
                raise IsolatedError('\n\n' + msg)
            elif status == (EXIT_SKIP_TEST << 8):
                raise SkipTest(msg)
            elif status == 0 and msg == '':
                pass
            else:
                raise RuntimeError('unexpected isolated process status {0}'.format(status))

    return wrapper

if 'coverage' in sys.modules:
    del fork_isolation  # quieten pyflakes
    def fork_isolation(f):
        # Fork isolation would break coverage measurements.
        # Oh well. FIXME.
        return f

__all__ = [
    'SkipTest',
    'assert_equal',
    'assert_greater_equal',
    'assert_is_instance',
    'assert_regexp_matches',
    'assert_rfc3339_timestamp',
    'assert_true',
    'fork_isolation',
    'interim',
    'interim_environ',
]

# vim:ts=4 sts=4 sw=4 et
