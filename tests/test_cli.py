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
import lib.xdg

from .tools import (
    assert_equal,
    assert_greater,
    assert_not_equal,
    interim,
    interim_environ,
)

@contextlib.contextmanager
def scan_config():
    tmpdir = tempfile.mkdtemp(prefix='scanhelper.')
    try:
        path = os.path.join(tmpdir, 'dll.conf')
        with open(path, 'wt', encoding='ASCII') as fp:
            fp.write('test')
        with interim_environ(SANE_CONFIG_DIR=tmpdir):
            with interim(lib.xdg, xdg_config_dirs=()):
                yield
    finally:
        shutil.rmtree(tmpdir)

def run_scanhelper(*args, stdin=None):
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdio = dict(
        stdout=stdout,
        stderr=stderr
    )
    if stdin:
        stdio.update(stdin=io.StringIO(stdin))
    argv = ['scanhelper']
    argv += args
    cwd = os.getcwd()
    with scan_config():
        with interim(sys, argv=argv, **stdio):
            try:
                lib.cli.main()
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
    args = [
        '-d', 'test:0',
        '--page-count=1',
    ]
    if xmp:
        args += ['--xmp']
    tmpdir = tempfile.mkdtemp(prefix='scanhelper.')
    try:
        args += [
            '--target-directory-prefix', os.path.join(tmpdir, 'test'),
        ]
        (rc, stdout, stderr) = run_scanhelper(*args, stdin='\n')
        paths = glob.glob(os.path.join(tmpdir, 'test-*', '*.png'))
        assert_not_equal(paths, [])
        assert_equal(len(paths), 1)
        [path] = paths
        with PIL.Image.open(path) as img:
            assert_equal(img.format, 'PNG')
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

def test_reconstruct_xpm():
    tmpdir = tempfile.mkdtemp(prefix='scanhelper.')
    try:
        with PIL.Image.new('L', (1, 1)) as img:
            path = os.path.join(tmpdir, 'test.png')
            img.save(path)
        (rc, stdout, stderr) = run_scanhelper('--reconstruct-xmp', path)
        with open(path + '.xmp', 'rb') as file:
            etree.parse(file)
    finally:
        shutil.rmtree(tmpdir)
    assert_equal(stdout, '')
    assert_equal(stderr, '')
    assert_equal(rc, 0)

def _test_not_implemented(arg):
    (rc, stdout, stderr) = run_scanhelper(arg)
    assert_equal(stdout, '')
    assert_equal(stderr, f'scanhelper: error: {arg} option is not yet supported\n')
    assert_equal(rc, 2)

def test_dont_scan():
    _test_not_implemented('--dont-scan')

def test_test():
    _test_not_implemented('--test')

def test_bad_device():
    (rc, stdout, stderr) = run_scanhelper('-d', '__bacon__')
    assert_equal(stdout, '')
    assert_equal(stderr, 'scanhelper: error: no such device: __bacon__\n')
    assert_equal(rc, 1)

def test_bad_button():
    args = [
        '-d', 'test:0',
        '--batch-button=__bacon__',
    ]
    tmpdir = tempfile.mkdtemp(prefix='scanhelper.')
    try:
        args += [
            '--target-directory-prefix', os.path.join(tmpdir, 'test'),
        ]
        (rc, stdout, stderr) = run_scanhelper(*args)
    finally:
        shutil.rmtree(tmpdir)
    assert_equal(stdout, '')
    stderr = stderr.splitlines(True)
    assert_equal(stderr[-1], 'scanhelper: error: no such button: __bacon__\n')
    assert_equal(rc, 1)

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

# TODO: add test for --override-xmp

# vim:ts=4 sts=4 sw=4 et
