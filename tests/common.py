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

def assert_regexp_matches(regexp, text):
    if isinstance(regexp, basestring):
        regexp = re.compile(regexp)
    if not regexp.search(text):
        message = "regexp doesn't match: {0!r} not found in {1!r}".format(regexp.pattern, text)
        raise AssertionError(message)

def assert_rfc3339_timestamp(timestamp):
    return assert_regexp_matches(
        '^[0-9]{4}(-[0-9]{2}){2}T[0-9]{2}(:[0-9]{2}){2}([+-][0-9]{2}:[0-9]{2}|Z)$',
        timestamp
    )

@contextlib.contextmanager
def exception(exc_type, string=None, regex=None, callback=None):
    if sum(x is not None for x in (string, regex, callback)) != 1:
        raise ValueError('exactly one of: string, regex, callback must be provided')
    if string is not None:
        def callback(exc):
            assert_equal(str(exc), string)
    elif regex is not None:
        def callback(exc):
            assert_regexp_matches(regex, str(exc))
    try:
        yield None
    except exc_type:
        _, exc, _ = sys.exc_info()
        callback(exc)
    else:
        message = '{0} was not raised'.format(exc_type.__name__)
        raise AssertionError(message)

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
    'assert_true',
    'assert_regexp_matches',
    'assert_rfc3339_timestamp',
    'fork_isolation',
    'interim',
    'interim_environ',
]

# vim:ts=4 sts=4 sw=4 et
