# encoding=UTF-8

# Copyright © 2024 Jakub Wilk <jwilk@jwilk.net>
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
import io
import os
import shutil
import sys
import tempfile

import lib.cli

from .tools import (
    assert_equal,
    assert_not_equal,
    interim,
    interim_environ,
)

@contextlib.contextmanager
def sane_config():
    tmpdir = tempfile.mkdtemp(prefix='scanhelper.')
    try:
        path = os.path.join(tmpdir, 'dll.conf')
        with open(path, 'w') as fp:
            fp.write('test')
        with interim_environ(SANE_CONFIG_DIR=tmpdir):
            yield
    finally:
        shutil.rmtree(tmpdir)

def run_scanhelper(*args):
    stdout = io.BytesIO()
    stderr = io.BytesIO()
    cmdline = ['scanhelper']
    cmdline += args
    with sane_config():
        with interim(sys, stdout=stdout, stderr=stderr):
            try:
                lib.cli.main(cmdline)
            except SystemExit as exc:
                rc = exc.code
            else:
                rc = 0
    return (rc, stdout.getvalue(), stderr.getvalue())

def test_L():
    (rc, stdout, stderr) = run_scanhelper('-L')
    assert_equal(stderr, '')
    assert_equal(rc, 0)
    assert_not_equal(stdout, '')

def test_help():
    (rc, stdout, stderr) = run_scanhelper('--help')
    assert_equal(stderr, '')
    assert_equal(rc, 0)
    assert_not_equal(stdout, '')

def test_version():
    (rc, stdout, stderr) = run_scanhelper('--version')
    assert_equal(stderr, '')
    assert_equal(rc, 0)
    assert_not_equal(stdout, '')

def test_bad_option():
    (rc, stdout, stderr) = run_scanhelper('--bad-option')
    assert_not_equal(stderr, '')
    assert_equal(rc, 1)
    assert_equal(stdout, '')

# vim:ts=4 sts=4 sw=4 et
