# encoding=UTF-8

# Copyright © 2012-2018 Jakub Wilk <jwilk@jwilk.net>
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

import time

from .tools import (
    assert_equal,
    assert_not_equal,
    assert_regex,
    assert_rfc3339_timestamp,
    fork_isolation,
    interim_environ,
)

from lib import xmp

def test_now():
    ts = xmp.now()
    assert_rfc3339_timestamp(str(ts))

def test_mtime():
    ts = xmp.mtime(__file__)
    assert_rfc3339_timestamp(str(ts))

def test_timezones():
    @fork_isolation
    def t(uts, tz, expected):
        with interim_environ(TZ=tz):
            time.tzset()
            ts = xmp.rfc3339(uts)
            assert_rfc3339_timestamp(str(ts))
            assert_equal(str(ts), expected)
    # winter:
    t(1261171514, 'UTC', '2009-12-18T21:25:14+00:00')
    t(1261171514, 'Europe/Warsaw', '2009-12-18T22:25:14+01:00')
    t(1261171514, 'America/New_York', '2009-12-18T16:25:14-05:00')
    t(1261171514, 'Asia/Kathmandu', '2009-12-19T03:10:14+05:45')
    t(1261171514, 'HAM+4:37', '2009-12-18T16:48:14-04:37')
    # summer:
    t(1337075844, 'Europe/Warsaw', '2012-05-15T11:57:24+02:00')
    # offset changes:
    t(1394737792, 'Europe/Moscow', '2014-03-13T23:09:52+04:00')  # used to be +04:00, but it's +03:00 now

_uuid_regex = (
    r'\Aurn:uuid:XXXXXXXX-XXXX-4XXX-[89ab]XXX-XXXXXXXXXXXX\Z'
    .replace('X', '[0-9a-f]')
)

def assert_uuid_urn(uuid):
    return assert_regex(
        uuid,
        _uuid_regex,
    )

def test_gen_uuid():
    uuid1 = xmp.gen_uuid()
    assert_uuid_urn(uuid1)
    uuid2 = xmp.gen_uuid()
    assert_uuid_urn(uuid2)
    assert_not_equal(uuid1, uuid2)

# vim:ts=4 sts=4 sw=4 et
