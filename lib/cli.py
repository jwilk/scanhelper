# encoding=UTF-8

# Copyright © 2011-2024 Jakub Wilk <jwilk@jwilk.net>
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

'''
scanhelper's command-line interface
'''

from __future__ import print_function

import argparse
import collections
import datetime
import distutils.version
import errno
import itertools
import logging
import os
import pty
import re
import shlex
import string
import sys
import time

from . import __version__
from . import gnu
from . import ipc
from . import scanner
from . import utils
from . import xdg
from . import xmp

file_formats = ('pnm', 'tiff', 'png')
media_types = dict(
    pnm='image/x-portable-anymap',
    tiff='image/tiff',
    png='image/png',
)

logger = None
ipc_logger = None

infinity = 1e999

class HelpAction(argparse.Action):

    def __call__(self, parser, namespace, values, option_string=None):
        parser.epilog = 'device-specific options:\n'
        if namespace.device is None:
            parser.epilog += '''  use 'scanhelper -d DEVICE --help' to get list of all options for DEVICE'''
        else:
            scanimage_args = ['--format=pnm', '-d', namespace.device, '--help']
            subprocess = run_scanimage(*scanimage_args, stdout=ipc.PIPE)
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

class VersionAction(argparse.Action):

    def __init__(self, option_strings, dest=argparse.SUPPRESS):
        super(VersionAction, self).__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=0,
            help="show program's version information and exit"
        )

    def __call__(self, parser, namespace, values, option_string=None):
        print('{prog} {0}'.format(__version__, prog=parser.prog))
        sane_version = scanner.get_sane_version()
        print('+ SANE {0}'.format(sane_version))
        scanimage_version = get_scanimage_version()
        if scanimage_version != sane_version:
            print('+ scanimage {0}'.format(scanimage_version))
        print('+ Python {0}.{1}.{2}'.format(*sys.version_info))
        pil_name = 'Pillow'
        try:
            pil_version = xmp.PIL.PILLOW_VERSION
        except AttributeError:
            try:
                pil_version = xmp.PIL.__version__
            except AttributeError:
                pil_name = 'PIL'
                pil_version = xmp.PIL.VERSION  # pylint: disable=no-member
        print('+ {PIL} {0}'.format(pil_version, PIL=pil_name))
        print('+ Jinja2 {0}'.format(xmp.jinja2.__version__))
        parser.exit()

class Config(object):

    @classmethod
    def get_paths(cls):
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
        argparse.ArgumentParser.__init__(self, add_help=False, formatter_class=argparse.RawDescriptionHelpFormatter)
        self.register('action', 'help', HelpAction)
        self.set_defaults(action='scan')
        sane_default_dev = os.getenv('SANE_DEFAULT_DEVICE') or None
        self.add_argument('-d', '--device-name', metavar='DEVICE', dest='device', default=sane_default_dev,
            help='use the given scanner device')
        self.add_argument('-L', '--list-devices', action='store_const', const='list_devices', dest='action',
            help='show available scanner devices')
        self.add_argument('--format', choices=file_formats, type=str.lower, dest='output_format', default='png',
            help='file format of output file (default: PNG)')
        self.add_argument('-t', '--target-directory', metavar='DIRECTORY',
            help='output directory (default: a unique, time-based directory is created)')
        self.add_argument('--target-directory-prefix', metavar='PREFIX',
            help='prefix for directory name if --target-directory is not used')
        self.add_argument('-i', '--icc-profile', metavar='PROFILE',
            help='include this ICC profile into TIFF file')
        self.add_argument('--accept-md5-only', action='store_true',
            help='only accept authorization requests using MD5')
        self.add_argument('-n', '--dont-scan', action='store_true',
            help='(not supported)')
        self.add_argument('-T', '--test', action='store_true',
            help='(not supported)')
        self.add_argument('-B', '--buffer-size', metavar='#', type=int, default=None,
            help='input buffer size (in kB; default: 32)')
        self.add_argument('-p', '--progress', action='store_true',
            help='print progress messages')
        self.add_argument('-v', '--verbose', action='store_true',
            help='more informational messages')
        self.add_argument('--profile')
        group = self.add_argument_group('batch mode')
        group.add_argument('-b', '--batch-mode', metavar='TEMPLATE', dest='filename_template',
            help='output filename template (default: p%%04d.<ext>)')
        group.add_argument('--batch-start', metavar='#', default=1, type=int,
            help='page number to start naming files with (default: 1)')
        group.add_argument('--batch-count', metavar='#', default=infinity, type=int,
            help='number of pages to scan in a single batch (default: no limit)')
        group.add_argument('--batch-increment', metavar='#', default=1, type=int,
            help='increase page number in filename by # (default: 1)')
        group.add_argument('--batch-double', action='store_const', dest='batch_increment', const=2,
            help='same as --batch-increment=2')
        group.add_argument('--batch-prompt', action='store_const', dest='batch_button', const=None,
            help='wait for ENTER before each batch (the default)')
        group.add_argument('--batch-button', metavar='BUTTON',
            help='wait for the scanner button before each batch')
        group.add_argument('--page-count', metavar='#', default=infinity, type=int,
            help='total number of pages to scan (default: no limit)')
        group.add_argument('--list-buttons', action='store_const', const='list_buttons', dest='action',
            help='show available buttons')
        group = self.add_argument_group('XMP support')
        group.add_argument('--xmp', action='store_true',
            help='create sidecar XMP metadata')
        group.add_argument('--reconstruct-xmp', nargs='+', metavar='IMAGE',
            help='reconstruct sidecar XMP metadata from existing files (only for advanced users)')
        group.add_argument('--override-xmp', nargs='+', action='append', default=[], metavar='KEY=VALUE',
            help='override an XMP metadata item (only for advanced users)')
        group = self.add_argument_group('auxiliary actions')
        group.add_argument('-h', '--help', action=HelpAction, nargs=0,
            help='show this help message and exit')
        group.add_argument('-V', '--version', action=VersionAction)
        group.add_argument('--show-config', action='store_const', const='show_config', dest='action',
            help='show status of configuration files')

    def do_not_print_usage(self, file=None):
        pass

    def xerror(self, message):
        self.print_usage = self.do_not_print_usage
        self.error(message)

    def parse_args(self, args=None, namespace=None):
        config = Config()
        if args is None:
            args = sys.argv[1:]
        my_args = list(args)
        my_args[:0] = config.get()
        result, extra_args = self.parse_known_args(my_args)
        if result.reconstruct_xmp:
            result.action = 'reconstruct_xmp'
        if result.profile is not None:
            my_args = list(args)
            try:
                my_args[:0] = config.get(result.profile)
            except KeyError:
                self.xerror('profile not found: {0!r}'.format(result.profile))
                raise ValueError
            my_args[:0] = config.get()
            result, extra_args = self.parse_known_args(my_args)
        result.config = config
        for opt in 'dont-scan', 'test':
            if getattr(result, opt.replace('-', '_')):
                self.xerror('--{0} option is not yet supported'.format(opt))
        result.extra_args = extra_args
        if result.filename_template is None:
            result.filename_template = 'p%04d.{0}'.format(result.output_format[:3])
        result.override_xmp = dict(
            item.split('=', 1)
            for items in result.override_xmp
            for item in items
        )
        return result

def list_devices(options):
    del options
    for d in scanner.get_devices():
        print(str.join('\t', d))

def get_device(options):
    scanners = scanner.get_devices()
    if not scanners:
        raise IndexError('no scanner devices')
    if options.device is None:
        if len(scanners) > 1:
            raise IndexError('please select a scanner device')
        name, vendor, model, type_ = scanners[0]
    else:
        for name, vendor, model, type_ in scanners:
            if name == options.device:
                break
        else:
            raise IndexError('no such device: {0}'.format(options.device))
    return scanner.Device(name, vendor, model, type_)

def error(message, *args, **kwargs):
    message = str(message)
    if args or kwargs:
        message = message.format(*args, **kwargs)
    print('scanhelper: error: {msg}'.format(msg=message), file=sys.stderr)
    sys.exit(1)

def list_buttons(options):
    try:
        device = get_device(options)
    except IndexError as exc:
        error(exc)
    for name in device:
        print(name)

def run_scanimage(*args, **kwargs):
    cmdline = ['scanimage']
    cmdline += args
    try:
        proc = ipc.Subprocess(cmdline, **kwargs)
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            message = 'scanimage not found; please install '
            if utils.debian:
                message += 'the sane-utils package'
            else:
                message += 'sane-backends <http://www.sane-project.org/>'
            error(message)
        raise
    return proc

def get_scanimage_args(options, device, start=0, count=infinity, increment=1):
    assert isinstance(device, scanner.Device)
    result = []
    result += ['--device-name', device.name]
    result += ['--format={0}'.format(options.output_format)]
    if options.icc_profile is not None:
        result += ['--icc-profile', options.icc_profile]
    result += ['--batch={template}'.format(
        template=options.filename_template,
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

def get_scanimage_version():
    proc = run_scanimage('--version', stdout=ipc.PIPE)
    line = proc.stdout.readline()
    proc.stdout.close()
    proc.wait()
    match = re.match('^scanimage [(]sane-backends[)] ([0-9.]+)', line)
    if match is None:
        error('cannot parse scanimage version')
    version = match.group(1)
    return distutils.version.LooseVersion(version)

def wait_for_button(device, button, sleep_interval=0.1):
    if button is None:
        raw_input('Press ENTER to continue\n')
        return
    if button not in device:
        error('no such button: {0}'.format(button))
    print('Press {0!r} button to continue'.format(button))
    while not device[button]:
        time.sleep(sleep_interval)

def scan_single_batch(options, device, start=0, count=infinity, increment=1):
    assert isinstance(device, scanner.Device)
    device.close()
    scanimage_args = get_scanimage_args(options, device, start, count, increment)
    master, slave = pty.openpty()
    master = os.fdopen(master, 'r', 1)
    subprocess = run_scanimage(*scanimage_args, stdout=slave, stderr=slave)
    os.close(slave)
    while True:
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
            yield int(match.group(1))
    try:
        subprocess.wait()
    except ipc.CalledProcessError as ex:
        if ex.returncode in {scanner.Status.NO_DOCS, scanner.Status.JAMMED}:
            pass
        else:
            raise

def create_unique_directory(prefix=''):
    alphabet = string.lowercase
    prefix += str(datetime.datetime.now()).replace(' ', 'T')[:19]
    for i in range(4):
        for suffix in itertools.product(*[alphabet] * i):
            path = prefix + str.join('', suffix)
            try:
                logger.debug('Trying to create target directory: %r', path)
                os.mkdir(path)
            except (OSError, IOError):
                continue
            return path
    raise  # pylint: disable=misplaced-bare-raise

def scan(options):
    if options.output_format == 'png':
        if get_scanimage_version() < '1.0.25':
            if utils.debian:
                pkg = 'sane-utils'
            else:
                pkg = 'scanimage (sane-backends)'
            error('PNG output format requires {pkg} >= 1.0.25'.format(pkg=pkg))
    try:
        device = get_device(options)
    except IndexError as exc:
        error(exc)
    assert isinstance(device, scanner.Device)
    target_directory = options.target_directory
    if target_directory is None:
        prefix = options.target_directory_prefix or ''
        if prefix and prefix[-1].isalnum():
            prefix += '-'
        target_directory = create_unique_directory(prefix)
        logger.info('Target directory: %s', target_directory)
    os.chdir(target_directory)
    start = options.batch_start
    increment = options.batch_increment
    batch_count = options.batch_count
    total_count = options.page_count
    ipc_logger.setLevel(logging.DEBUG)
    try:
        while total_count > 0:
            try:
                wait_for_button(device, options.batch_button)
            except EOFError:
                return
            for page in scan_single_batch(options, device, start, min(total_count, batch_count), increment):
                del page
                image_filename = gnu.sprintf(options.filename_template, start)
                if options.xmp:
                    real_image_filename = image_filename
                    xmp_filename = image_filename + '.xmp'
                    override = dict(
                        media_type=media_types[options.output_format],
                    )
                    override.update(options.override_xmp)
                    with open(xmp_filename, 'w') as xmp_file:
                        xmp.write(
                            xmp_file=xmp_file,
                            image_filename=real_image_filename,
                            device=device,
                            override=override
                        )
                start += increment
                total_count -= 1
    except KeyboardInterrupt:
        logger.info('Interrupted by user')
        # TODO: re-raise SIGINT

def reconstruct_xmp(options):
    class device:
        vendor = None
        model = None
    if ('device_vendor' in options.override_xmp and 'device_model' in options.override_xmp):
        # Don't bother running get_device(), as it's time consuming.
        pass
    else:
        assert device  # quieten pyflakes
        try:
            device = get_device(options)
        except IndexError:
            pass
        else:
            assert isinstance(device, scanner.Device)
    for image_filename in options.reconstruct_xmp:
        xmp_filename = image_filename + '.xmp'
        with open(xmp_filename, 'w') as xmp_file:
            xmp.write(
                xmp_file=xmp_file,
                image_filename=image_filename,
                device=device,
                override=options.override_xmp
            )

def unexpand_tilde(path):
    home = os.path.expanduser('~/')
    if path.startswith(home):
        path = '~/' + path[len(home):]
    return path

def show_config(options):
    esc = ipc.shell_escape
    print('Configuration files:')
    for path in options.config.get_paths():
        path = unexpand_tilde(path)
        print('    {0}'.format(path))
    extra_options = options.config.get(None)
    print()
    if extra_options:
        print('Default options:')
        print('    {0}'.format(esc(extra_options)))
    else:
        print('No default options')
    i = 0
    for profile in options.config.get_profiles():
        print()
        print('Options for profile {0!r}:'.format(profile))
        extra_options = options.config.get(profile)
        print('    {0}'.format(esc(extra_options)))
        i += 1
    if i == 0:
        print()
        print('No profiles')
    print()

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
    global ipc_logger
    ipc_logger = logging.getLogger('scanhelper.ipc')
    formatter = logging.Formatter('+ %(message)s')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    ipc_logger.addHandler(handler)
    ipc_logger.setLevel(logging.INFO)

def main():
    setup_logging()
    parser = ArgumentParser()
    options = parser.parse_args()
    action = globals()[options.action]
    if options.verbose:
        logger.setLevel(logging.DEBUG)
    return action(options)

__all__ = ['main']

# vim:ts=4 sts=4 sw=4 et
