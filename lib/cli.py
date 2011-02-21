# encoding=UTF-8

# Copyright © 2011 Jakub Wilk <jwilk@jwilk.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 dated June, 1991.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.

__version__ = '0.0'

import datetime
import itertools
import logging
import os
import pty
import re
import shlex
import sys
import time

from . import gnu
from . import ipc
from . import scanner
from . import utils

try:
    import argparse
except ImportError, ex:
    utils.enhance_import_error(ex, 'argparse', 'python-argparse', 'http://code.google.com/p/argparse/')
    raise

try:
    import xdg.BaseDirectory as xdg
except ImportError, ex:
    utils.enhance_import_error(ex, 'PyXDG', 'python-xdg', 'http://www.freedesktop.org/wiki/Software/pyxdg')
    raise

try:
    import ExactImage as exactimage
except ImportError, ex:
    utils.enhance_import_error(ex, 'ExactImage', 'python-exactimage', 'http://www.exactcode.de/site/open_source/exactimage/')
    raise

scanimage_file_formats = ('pnm', 'tiff')
file_formats = scanimage_file_formats + ('png',)

logger = None

infinity = 1.0e9999

class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        version = '%(prog)s ' + __version__
        argparse.ArgumentParser.__init__(self)
        self.set_defaults(action='scan')
        self.add_argument('-d', '--device-name', metavar='DEVICE', dest='device', help='use a given scanner device')
        self.add_argument('--format', choices=file_formats, dest='output_format', default='png', help='file format of output file')
        self.add_argument('-t', '--target-directory', metavar='DIRECTORY', help='output directory')
        self.add_argument('-i', '--icc-profile', metavar='PROFILE', help='include this ICC profile into TIFF file')
        self.add_argument('-L', '--list-devices', action='store_const', const='list_devices', dest='action', help='show available scanner devices')
        self.add_argument('--list-buttons', action='store_const', const='list_buttons', dest='action', help='show available buttons')
        self.add_argument('-b', '--batch-mode', metavar='TEMPLATE', dest='filename_template', help='output filename template')
        self.add_argument('--batch-start', metavar='#', default=1, type=int, help='page number to start naming files with')
        self.add_argument('--batch-count', metavar='#', default=infinity, type=int, help='how many pages to scan in batch mode')
        self.add_argument('--batch-increment', metavar='#', default=1, type=int, help='increase page number in filename by #')
        self.add_argument('--batch-double', action='store_const', dest='batch_increment', const=2, help='same as --batch-increment=2')
        self.add_argument('--batch-prompt', action='store_true', help='(not supported)')
        self.add_argument('--batch-button', metavar='BUTTON', help='button triggering next batch')
        self.add_argument('--accept-md5-only', action='store_true', help='only accept authorization requests using MD5')
        self.add_argument('-p', '--progress', action='store_true', help='print progress messages')
        self.add_argument('-n', '--dont-scan', action='store_true', help='(not supported)')
        self.add_argument('-T', '--test', action='store_true', help='(not supported)')
        self.add_argument('-v', '--verbose', action='store_true', help='more informational messages')
        self.add_argument('-B', '--buffer-size', metavar='#', type=int, default=None, help='input buffer size (in kB, default 32)')
        self.add_argument('-V', '--version', action='version', version=version, help='show version information and exit')

    def parse_args(self, args, namespace=None):
        for config in reversed(list(xdg.load_config_paths('scanhelper'))):
            with open(config, 'r') as config:
                extra_args = config.read()
            extra_args = shlex.split(extra_args)
            args[1:1] = extra_args
        result, extra_args = self.parse_known_args()
        for opt in 'batch-prompt', 'dont-scan', 'test':
            if getattr(result, opt.replace('-', '_')):
                raise NotImplementedError('The --{0} option is not yet supported'.format(opt))
        result.extra_args = extra_args
        if result.filename_template is None:
            result.filename_template = 'p%04d.{0}'.format(result.output_format[:3])
        if result.device is None:
            result.device = os.getenv('SANE_DEFAULT_DEVICE') or None
        return result

def list_devices(options):
    for d in scanner.get_devices():
        print '%-24s %r' % (d[0], d[1:])

def get_device(options):
    if options.device is None:
        info = scanner.get_devices()
        if len(info) == 0:
            raise IndexError('No scanner devices')
        elif len(info) > 1:
            raise IndexError('Please select a scanner device')
        name = info[0][0]
    else:
        name = options.device
    return scanner.Device(name)

def list_buttons(options):
    device = get_device(options)
    for name in device:
        print name

def get_scanimage_commandline(options, device, start=0, count=infinity, increment=1):
    assert isinstance(device, scanner.Device)
    result = ['scanimage']
    result += ['--device-name', device.name]
    result += ['--format={0}'.format('pnm' if options.output_format == 'pnm' else 'tiff')]
    if options.icc_profile is not None:
        result +=['--icc-profile', options.icc_profile]
    result += ['--batch={0}'.format(options.filename_template)]
    if start >= 0:
        result += ['--batch-start={0}'.format(start)]
    if count < infinity:
        result += ['--batch-count={0}'.format(count)]
    if increment > 1:
        result += ['--batch-increment={0}'.format(increment)]
    if options.accept_md5_only:
        result += ['--accept-md5-only']
    if options.progress:
        result += ['--progress']
    if options.verbose:
        result += ['--verbose']
    if options.buffer_size is not None:
        result += ['--buffer-size={0}'.format(options.buffer_size)]
    assert all(isinstance(x, str) for x in result)
    return result + options.extra_args

def wait_for_button(device, button, sleep_interval=0.1):
    if button is None:
        return
    print 'Press %r button to continue' % button
    while not device[button]:
        time.sleep(sleep_interval)

def scan_single_batch(options, device, start=0, count=infinity, increment=1):
    assert isinstance(device, scanner.Device)
    device.close()
    result = []
    commandline = get_scanimage_commandline(options, device, start, count, increment)
    master, slave = pty.openpty()
    master = os.fdopen(master, 'r', 1)
    subprocess = ipc.Subprocess(commandline, stdout=slave, stderr=slave)
    os.close(slave)
    while 1:
        try:
            line = master.readline()
        except IOError:
            break
        if line == '':
            break
        sys.stdout.flush()
        match = re.match('Scanned page ([0-9]+)', line)
        if match:
            result += [int(match.group(1), 10)]
        sys.stdout.write('| ' + line)
        sys.stdout.flush()
    try:
        subprocess.wait()
    except ipc.CalledProcessError, ex:
        if ex.returncode == scanner.STATUS_NO_DOCS:
            pass
        else:
            raise
    return result

def create_temporary_directory():
    alphabet = [chr(c) for c in xrange(ord('a'), ord('z') + 1)]
    prefix = str(datetime.datetime.now()).replace(' ', 'T')[:19]
    for i in 0, 1, 2, 3:
        for suffix in itertools.product(*[alphabet] * i):
            path = prefix + ''.join(suffix)
            try:
                logger.debug('Trying to create target directory: %r', path)
                os.mkdir(path)
            except (OSError, IOError):
                continue
            return path
    raise

def convert(filename):
    image = exactimage.newImage()
    logger.debug('Converting %s', filename)
    exactimage.decodeImageFile(image, filename)
    exactimage.encodeImageFile(image, filename)

def scan(options):
    device = get_device(options)
    assert isinstance(device, scanner.Device)
    target_directory = options.target_directory
    if target_directory is None:
        target_directory = create_temporary_directory()
        logger.info('Target directory: %s', target_directory)
    os.chdir(target_directory)
    start = options.batch_start
    count = options.batch_count
    increment = options.batch_increment
    while count > 0:
        wait_for_button(device, options.batch_button)
        pages = scan_single_batch(options, device, start, count, increment)
        if len(pages) == 0:
            break
        filenames = [gnu.sprintf(options.filename_template, n) for n in pages]
        if options.output_format not in scanimage_file_formats:
            for filename in filenames:
                convert(filename)
        count -= len(pages)
        start += len(pages) * increment

def setup_logging():
    # Main logger:
    global logger
    logger = logging.getLogger('scanhelper.main')
    formatter = logging.Formatter('%(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # IPC logger:
    ipc_logger = logging.getLogger('scanhelper.ipc')
    formatter = logging.Formatter('+ %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    ipc_logger.addHandler(handler)
    ipc_logger.setLevel(logging.DEBUG)

def main(args):
    setup_logging()
    parser = ArgumentParser()
    options = parser.parse_args(args)
    action = globals()[options.action]
    return action(options)

# vim:ts=4 sw=4 et
