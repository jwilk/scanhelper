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

from __future__ import print_function

import errno
import locale
import os
import signal
import stat
import tempfile
import shutil

from tests.common import (
    SkipTest,
    assert_equal,
    assert_true,
    exception,
    interim_environ,
)

from lib import ipc

nonexistent_command = 'didjvu-nonexistent-command'

class test_exceptions():

    def test_valid(self):
        def t(name):
            signo = getattr(signal, name)
            ex = ipc.CalledProcessInterrupted(signo, 'eggs')
            assert_equal(str(ex), "Command 'eggs' was interrupted by signal " + name)
        for name in 'SIGINT', 'SIGABRT', 'SIGSEGV':
            yield t, name

    def test_invalid_signo(self):
        # signal.NSIG is guaranteed not be a correct signal number
        ex = ipc.CalledProcessInterrupted(signal.NSIG, 'eggs')
        assert_equal(str(ex), "Command 'eggs' was interrupted by signal {0}".format(signal.NSIG))

class test_wait():

    def test0(self):
        child = ipc.Subprocess(['true'])
        child.wait()

    def test1(self):
        child = ipc.Subprocess(['false'])
        with exception(ipc.CalledProcessError, "Command 'false' returned non-zero exit status 1"):
            child.wait()

    def _test_signal(self, name):
        child = ipc.Subprocess(['cat'], stdin=ipc.PIPE)  # Any long-standing process would do.
        os.kill(child.pid, getattr(signal, name))
        with exception(ipc.CalledProcessInterrupted, "Command 'cat' was interrupted by signal " + name):
            child.wait()

    def test_wait_signal(self):
        for name in 'SIGINT', 'SIGABRT', 'SIGSEGV':
            yield self._test_signal, name

utf8_locale_candidates = ['C.UTF-8', 'en_US.UTF-8']

def get_utf8_locale():
    old_locale = locale.setlocale(locale.LC_ALL)
    try:
        for new_locale in utf8_locale_candidates:
            try:
                locale.setlocale(locale.LC_ALL, new_locale)
            except locale.Error:
                continue
            return new_locale
    finally:
        locale.setlocale(locale.LC_ALL, old_locale)

utf8_locale = get_utf8_locale()

class test_environment():

    def test1(self):
        with interim_environ(didjvu='42'):
            child = ipc.Subprocess(
                ['sh', '-c', 'printf $didjvu'],
                stdout=ipc.PIPE, stderr=ipc.PIPE,
            )
            stdout, stderr = child.communicate()
            assert_equal(stdout, '42')
            assert_equal(stderr, '')

    def test2(self):
        with interim_environ(didjvu='42'):
            child = ipc.Subprocess(
                ['sh', '-c', 'printf $didjvu'],
                stdout=ipc.PIPE, stderr=ipc.PIPE,
                env={},
            )
            stdout, stderr = child.communicate()
            assert_equal(stdout, '42')
            assert_equal(stderr, '')

    def test3(self):
        with interim_environ(didjvu='42'):
            child = ipc.Subprocess(
                ['sh', '-c', 'printf $didjvu'],
                stdout=ipc.PIPE, stderr=ipc.PIPE,
                env=dict(didjvu='24'),
            )
            stdout, stderr = child.communicate()
            assert_equal(stdout, '24')
            assert_equal(stderr, '')

    def test_path(self):
        path = os.getenv('PATH').split(':')
        tmpdir = tempfile.mkdtemp(prefix='scanhelper.')
        try:
            command_name = 'eggs'
            command_path = os.path.join(tmpdir, command_name)
            with open(command_path, 'wt') as file:
                print('#!/bin/sh', file=file)
                print('printf 42', file=file)
            os.chmod(command_path, stat.S_IRWXU)
            path[:0] = [tmpdir]
            path = ':'.join(path)
            with interim_environ(PATH=path):
                child = ipc.Subprocess([command_name],
                    stdout=ipc.PIPE, stderr=ipc.PIPE,
                )
                stdout, stderr = child.communicate()
                assert_equal(stdout, '42')
                assert_equal(stderr, '')
        finally:
            shutil.rmtree(tmpdir)

    def _test_locale(self):
        child = ipc.Subprocess(['locale'],
            stdout=ipc.PIPE, stderr=ipc.PIPE
        )
        stdout, stderr = child.communicate()
        stdout = stdout.splitlines()
        stderr = stderr.splitlines()
        assert_equal(stderr, [])
        data = dict(line.split('=', 1) for line in stdout)
        has_lc_all = has_lc_ctype = has_lang = 0
        for key, value in data.iteritems():
            if key == 'LC_ALL':
                has_lc_all = 1
                assert_equal(value, '')
            elif key == 'LC_CTYPE':
                has_lc_ctype = 1
                if utf8_locale is None:
                    raise SkipTest(
                        'UTF-8 locale missing '
                        '({0})'.format(' or '.join(utf8_locale_candidates))
                    )
                assert_equal(value, utf8_locale)
            elif key == 'LANG':
                has_lang = 1
                assert_equal(value, '')
            elif key == 'LANGUAGE':
                assert_equal(value, '')
            else:
                assert_equal(value, '"POSIX"')
        assert_true(has_lc_all)
        assert_true(has_lc_ctype)
        assert_true(has_lang)

    def test_locale_lc_all(self):
        with interim_environ(LC_ALL=utf8_locale):
            self._test_locale()

    def test_locale_lc_ctype(self):
        with interim_environ(LC_ALL=None, LC_CTYPE=utf8_locale):
            self._test_locale()

    def test_locale_lang(self):
        with interim_environ(LC_ALL=None, LC_CTYPE=None, LANG=utf8_locale):
            self._test_locale()

def test_init_exception():
    exc_message = "[Errno {errno.ENOENT}] No such file or directory: {cmd!r}".format(
        errno=errno,
        cmd=nonexistent_command,
    )
    with exception(OSError, exc_message):
        ipc.Subprocess([nonexistent_command])

class test_shell_escape():

    def test_no_escape(self):
        s = 'eggs'
        r = ipc.shell_escape(s)
        assert_equal(r, s)

    def test_escape(self):
        s = '$pam'
        r = ipc.shell_escape(s)
        assert_equal(r, "'$pam'")
        s = "s'pam"
        r = ipc.shell_escape(s)
        assert_equal(r, "'s'\\''pam'")

    def test_list(self):
        l = ['$pam', 'eggs', "s'pam"]
        r = ipc.shell_escape_list(l)
        assert_equal(r, "'$pam' eggs 's'\\''pam'")


# vim:ts=4 sts=4 sw=4 et