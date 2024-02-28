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
import glob
import io
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as etree

import PIL.Image

import lib.cli

from .tools import (
    assert_equal,
    assert_greater,
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

def run_scanhelper(*args, **kwargs):
    stdout = io.BytesIO()
    stderr = io.BytesIO()
    stdio = dict(
        stdout=stdout,
        stderr=stderr
    )
    if kwargs:
        stdin = kwargs.pop('stdin')
        assert not kwargs
        stdio.update(stdin=io.BytesIO(stdin))
    argv = ['scanhelper']
    argv += args
    cwd = os.getcwd()
    with sane_config():
        with interim(sys, argv=argv, **stdio):
            try:
                lib.cli.main(argv)
            except SystemExit as exc:
                rc = exc.code
            else:
                rc = 0
            finally:
                os.chdir(cwd)
    return (rc, stdout.getvalue(), stderr.getvalue())

def test_list_devices():
    (rc, stdout, stderr) = run_scanhelper('-L')
    assert_equal(stderr, '')
    assert_equal(rc, 0)
    assert_not_equal(stdout, '')

def test_list_buttons():
    (rc, stdout, stderr) = run_scanhelper('-d', 'test:0', '--list-buttons')
    assert_equal(stderr, '')
    assert_equal(rc, 0)
    assert_not_equal(stdout, '')

def test_scanning(xmp=False):
    tmpdir = tempfile.mkdtemp(prefix='scanhelper.')
    args = [
        '-d', 'test:0',
        '--page-count=1',
        '--target-directory-prefix', os.path.join(tmpdir, 'test'),
    ]
    if xmp:
        args += ['--xmp']
    try:
        (rc, stdout, stderr) = run_scanhelper(*args, stdin=b'\n')
        paths = glob.glob(os.path.join(tmpdir, 'test-*', '*.png'))
        assert_not_equal(paths, [])
        assert_equal(len(paths), 1)
        [path] = paths
        img = PIL.Image.open(path)
        try:
            assert_equal(img.format, 'PNG')
        finally:
            img.close()
        if xmp:
            with open(path + '.xmp', 'rb') as file:
                etree.parse(file)
    finally:
        shutil.rmtree(tmpdir)
    assert_equal(rc, 0)
    assert_not_equal(stderr, '')
    assert_not_equal(stdout, '')

def test_scanning_xmp():
    test_scanning(xmp=True)

def _test_not_implemented(arg):
    (rc, stdout, stderr) = run_scanhelper(arg)
    assert_equal(stdout, '')
    assert_equal(stderr, 'scanhelper: error: {arg} option is not yet supported\n'.format(arg=arg))
    assert_equal(rc, 2)

def test_dont_scan():
    _test_not_implemented('--dont-scan')

def test_test():
    _test_not_implemented('--test')

def test_help():
    (rc, stdout, stderr) = run_scanhelper('--help')
    assert_equal(stderr, '')
    assert_equal(rc, 0)
    assert_not_equal(stdout, '')
    (rc, stdout_d, stderr) = run_scanhelper('-d', 'test:0', '--help')
    assert_equal(stderr, '')
    assert_equal(rc, 0)
    assert_not_equal(stdout_d, '')
    assert_greater(len(stdout_d), len(stdout))

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
