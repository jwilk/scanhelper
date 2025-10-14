# encoding=UTF-8

# Copyright © 2010-2024 Jakub Wilk <jwilk@jwilk.net>
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

import contextlib
import functools
import os
import sys
import traceback

# TODO: migrate away from nose
from nose import SkipTest
from nose.tools import (  # pylint: disable=no-name-in-module
    assert_equal,
    assert_greater,
    assert_greater_equal,
    assert_is_instance,
    assert_not_equal,
    assert_raises,
    assert_regex,
    assert_true,
)

def assert_fail(msg):
    assert_true(False, msg=msg)  # pylint: disable=redundant-unittest-assert

def assert_rfc3339_timestamp(timestamp):
    return assert_regex(
        timestamp,
        '^[0-9]{4}(-[0-9]{2}){2}T[0-9]{2}(:[0-9]{2}){2}([+-][0-9]{2}:[0-9]{2}|Z)$',
    )

@contextlib.contextmanager
def interim(obj, **override):
    copy = {
        key: getattr(obj, key)
        for key in override
    }
    for key, value in override.items():
        setattr(obj, key, value)
    try:
        yield
    finally:
        for key, value in copy.items():
            setattr(obj, key, value)

@contextlib.contextmanager
def interim_environ(**override):
    keys = set(override)
    copy_keys = keys & set(os.environ)
    copy = {
        key: value
        for key, value in os.environ.items()
        if key in copy_keys
    }
    for key, value in override.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key in keys:
            os.environ.pop(key, None)
        os.environ.update(copy)

class IsolatedException(Exception):
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

    exit = os._exit  # pylint: disable=protected-access,redefined-builtin
    # sys.exit() can't be used here, because nose catches all exceptions,
    # including SystemExit

    # pylint:disable=consider-using-sys-exit

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        readfd, writefd = os.pipe()
        pid = os.fork()
        if pid == 0:
            # child:
            os.close(readfd)
            try:
                f(*args, **kwargs)
            except SkipTest as exc:
                s = str(exc)
                with os.fdopen(writefd, 'wb') as fp:
                    fp.write(s)
                exit(EXIT_SKIP_TEST)
            except Exception:  # pylint: disable=broad-except
                exctp, exc, tb = sys.exc_info()
                s = traceback.format_exception(exctp, exc, tb, _n_relevant_tb_levels(tb))
                s = str.join('', s).encode('UTF-8')
                del tb
                with os.fdopen(writefd, 'wb') as fp:
                    fp.write(s)
                exit(EXIT_EXCEPTION)
            exit(0)
        else:
            # parent:
            os.close(writefd)
            with os.fdopen(readfd, 'rb') as fp:
                msg = fp.read()
            msg = msg.decode('UTF-8').rstrip('\n')
            pid, status = os.waitpid(pid, 0)
            if status == (EXIT_EXCEPTION << 8):
                raise IsolatedException('\n\n' + msg)
            elif status == (EXIT_SKIP_TEST << 8):
                raise SkipTest(msg)
            elif status == 0 and msg == '':
                pass
            else:
                raise RuntimeError(f'unexpected isolated process status {status}')

    return wrapper

if 'coverage' in sys.modules:
    assert fork_isolation  # quieten pyflakes
    def fork_isolation(f):  # pylint: disable=function-redefined
        # Fork isolation would break coverage measurements.
        # Oh well. FIXME.
        return f

__all__ = [
    # nose:
    'SkipTest',
    'assert_equal',
    'assert_greater',
    'assert_greater_equal',
    'assert_is_instance',
    'assert_not_equal',
    'assert_raises',
    'assert_regex',
    'assert_true',
    # misc:
    'assert_rfc3339_timestamp',
    'fork_isolation',
    'interim',
    'interim_environ',
]

# vim:ts=4 sts=4 sw=4 et
