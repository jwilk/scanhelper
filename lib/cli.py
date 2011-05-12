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

import collections
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

temporary_suffix = '.tmp.scanhelper~'
scanimage_file_formats = ('pnm', 'tiff')
file_formats = scanimage_file_formats + ('png',)

logger = None

infinity = 1.0e9999

class HelpAction(argparse.Action):

    def __call__(self, parser, namespace, values, option_string=None):
        parser.epilog = 'device-specific options:\n'
        if namespace.device is None:
            parser.epilog += '''  use 'scanhelper -d DEVICE --help' to get list of all optons for DEVICE'''
        else:
            commandline = ['scanimage', '-d', namespace.device, '--help']
            subprocess = ipc.Subprocess(commandline, stdout=ipc.PIPE)
            for line in subprocess.stdout:
                if not line.startswith('Options specific to device'):
                    continue
                else:
                    break
            for line in subprocess.stdout:
                if line.strip():
                    parser.epilog += line
                else:
                    break
            subprocess.stdout.close()
            subprocess.wait()
        parser.print_help()
        parser.exit()

class Config(object):

    @classmethod
    def get_paths(cls, writable=True):
        xdg.save_config_path('scanhelper')
        for x in xdg.load_config_paths('scanhelper'):
            yield os.path.join(x, 'config')

    def __init__(self):
        self._data = data = collections.defaultdict(list)
        data[None] = []
        for config in self.get_paths():
            if not os.path.exists(config):
                continue
            with open(config, 'r') as config:
                for line in config:
                    if not line:
                        continue
                    if line[0] == '-' or line[0].isspace() or ':' not in line:
                        profile = None
                    else:
                        profile, _, line = line.partition(':')
                        profile = profile.strip()
                    self._data[profile] += shlex.split(line)

    def get_profiles(self):
        result = set(self._data.keys())
        result.remove(None)
        return result

    def get(self, profile=None):
        if profile is None:
            return self._data[None]
        else:
            if profile not in self._data:
                raise KeyError(profile)
            return self._data[profile]

class ArgumentParser(argparse.ArgumentParser):

    def __init__(self):
        version = '%(prog)s ' + __version__
        argparse.ArgumentParser.__init__(self, add_help=False, formatter_class=argparse.RawDescriptionHelpFormatter)
        self.register('action', 'help', HelpAction)
        self.set_defaults(action='scan')
        self.add_argument('-d', '--device-name', metavar='DEVICE', dest='device', default=os.getenv('SANE_DEFAULT_DEVICE') or None, help='use a given scanner device')
        self.add_argument('--format', choices=file_formats, dest='output_format', default='png', help='file format of output file (default: PNG)')
        self.add_argument('-t', '--target-directory', metavar='DIRECTORY', help='output directory (default: an unique, time-based directory is created)')
        self.add_argument('--target-directory-prefix', metavar='PREFIX', help='prefix for directory name if --target-directory is not used')
        self.add_argument('-i', '--icc-profile', metavar='PROFILE', help='include this ICC profile into TIFF file')
        self.add_argument('-L', '--list-devices', action='store_const', const='list_devices', dest='action', help='show available scanner devices')
        self.add_argument('--list-buttons', action='store_const', const='list_buttons', dest='action', help='show available buttons')
        self.add_argument('-b', '--batch-mode', metavar='TEMPLATE', dest='filename_template', help='output filename template (default: p%%04d.<ext>)')
        self.add_argument('--batch-start', metavar='#', default=1, type=int, help='page number to start naming files with (default: 1)')
        self.add_argument('--batch-count', metavar='#', default=infinity, type=int, help='how many pages to scan in batch mode (default: no limit)')
        self.add_argument('--batch-increment', metavar='#', default=1, type=int, help='increase page number in filename by # (default: 1)')
        self.add_argument('--batch-double', action='store_const', dest='batch_increment', const=2, help='same as --batch-increment=2')
        self.add_argument('--batch-prompt', action='store_true', help='(not supported)')
        self.add_argument('--batch-button', metavar='BUTTON', help='button triggering next batch')
        self.add_argument('--accept-md5-only', action='store_true', help='only accept authorization requests using MD5')
        self.add_argument('-p', '--progress', action='store_true', help='print progress messages')
        self.add_argument('-n', '--dont-scan', action='store_true', help='(not supported)')
        self.add_argument('-T', '--test', action='store_true', help='(not supported)')
        self.add_argument('-v', '--verbose', action='store_true', help='more informational messages')
        self.add_argument('-B', '--buffer-size', metavar='#', type=int, default=None, help='input buffer size (in kB; default: 32)')
        self.add_argument('--profile')
        group = self.add_argument_group('auxiliary actions')
        group.add_argument('-h', '--help', action=HelpAction, nargs=0, help='show this help message and exit')
        group.add_argument('-V', '--version', action='version', version=version, help='show version information and exit')
        group.add_argument('--clean-temporary-files', action='store_const', const='clean_temporary_files', dest='action', help='clean temporary files that might have been left by aborted runs of scanhelper')
        group.add_argument('--show-config', action='store_const', const='show_config', dest='action', help='show status of configuration files')

    def parse_args(self, args, namespace=None):
        config = Config()
        my_args = args[1:]
        my_args[:0] = config.get()
        result, extra_args = self.parse_known_args(my_args)
        if result.profile is not None:
            my_args = args[1:]
            my_args[:0] = config.get(result.profile)
            my_args[:0] = config.get()
            result, extra_args = self.parse_known_args(my_args)
        result.config = config
        for opt in 'batch-prompt', 'dont-scan', 'test':
            if getattr(result, opt.replace('-', '_')):
                raise NotImplementedError('The --{0} option is not yet supported'.format(opt))
        result.extra_args = extra_args
        if result.filename_template is None:
            result.filename_template = 'p%04d.{0}'.format(result.output_format[:3])
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
    result += ['--batch={template}{suffix}'.format(
        template=options.filename_template,
        suffix=('' if options.output_format in scanimage_file_formats else temporary_suffix)
    )]
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
        sys.stdout.write('| ' + line)
        sys.stdout.flush()
        if match:
            yield int(match.group(1), 10)
    try:
        subprocess.wait()
    except ipc.CalledProcessError, ex:
        if ex.returncode in (scanner.STATUS_NO_DOCS, scanner.STATUS_JAMMED):
            pass
        else:
            raise

def create_unique_directory(prefix=''):
    alphabet = [chr(c) for c in xrange(ord('a'), ord('z') + 1)]
    prefix += str(datetime.datetime.now()).replace(' ', 'T')[:19]
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
    exactimage.decodeImageFile(image, filename + temporary_suffix)
    exactimage.encodeImageFile(image, filename)
    os.stat(filename)
    os.remove(filename + temporary_suffix)
    exactimage.deleteImage(image)

def scan(options):
    device = get_device(options)
    assert isinstance(device, scanner.Device)
    target_directory = options.target_directory
    if target_directory is None:
        prefix = options.target_directory_prefix or ''
        if len(prefix) > 0 and prefix[-1].isalnum():
            prefix += '-'
        target_directory = create_unique_directory(prefix)
        logger.info('Target directory: %s', target_directory)
    os.chdir(target_directory)
    start = options.batch_start
    count = options.batch_count
    increment = options.batch_increment
    while count > 0:
        wait_for_button(device, options.batch_button)
        for page in scan_single_batch(options, device, start, count, increment):
            filename= gnu.sprintf(options.filename_template, start)
            if options.output_format not in scanimage_file_formats:
                convert(filename)
            start += increment
            count -= 1

def clean_temporary_files(options):
    if options.target_directory is None:
        ArgumentParser().error('--target-directory is obligatory with --clean-temporary-files')
    i = 0
    for root, dirs, files in os.walk(options.target_directory):
        for filename in files:
            filename = os.path.join(root, filename)
            if filename.endswith(temporary_suffix):
                convert(filename[:-len(temporary_suffix)])
                i += 1
    logger.info(
        'No files have been converted' if i == 0
        else '1 file has been convert' if i == 1
        else '{0} files have been converted'.format(i)
    )

def show_config(options):
    tilde = os.path.expanduser('~')
    print 'Configuration files:'
    for filename in options.config.get_paths(writable=True):
        if filename.startswith(tilde):
            filename = '~' + filename[len(tilde):]
        print '    {0}'.format(filename)
    extra_options = options.config.get(None)
    print
    if extra_options:
        print 'Default options:'
        print '    {0}'.format(utils.shell_escape_list(extra_options))
    else:
        print 'No default options'
    i = 0
    for profile in options.config.get_profiles():
        print
        print 'Options for profile {0!r}:'.format(profile)
        extra_options = options.config.get(profile)
        print '    {0}'.format(utils.shell_escape_list(extra_options))
        i += 1
    if i == 0:
        print
        print 'No profiles'
    print

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
    if options.verbose:
        logger.setLevel(logging.DEBUG)
    return action(options)

# vim:ts=4 sw=4 et
