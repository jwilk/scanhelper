# encoding=UTF-8

# Copyright © 2011-2015 Jakub Wilk <jwilk@jwilk.net>
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

import Queue as queue
import collections
import datetime
import itertools
import logging
import os
import pty
import re
import shlex
import sys
import threading
import time

from . import __version__
from . import gnu
from . import ipc
from . import scanner
from . import utils
from . import xdg
from . import xmp

try:
    import argparse
except ImportError as ex:
    utils.enhance_import_error(ex, 'argparse', 'python-argparse', 'https://pypi.python.org/pypi/argparse')
    raise

try:
    import PIL.Image as pil
except ImportError as ex:
    utils.enhance_import_error(ex, 'Python Imaging Library', 'python-imaging', 'http://www.pythonware.com/products/pil/')
    raise

temporary_suffix = '.tmp.scanhelper~'
scanimage_file_formats = ('pnm', 'tiff')
file_formats = scanimage_file_formats + ('png',)
media_types = dict(
    pnm='image/x-portable-anymap',
    tiff='image/tiff',
    png='image/png',
)

logger = None

infinity = 1.0e9999

class HelpAction(argparse.Action):

    def __call__(self, parser, namespace, values, option_string=None):
        parser.epilog = 'device-specific options:\n'
        if namespace.device is None:
            parser.epilog += '''  use 'scanhelper -d DEVICE --help' to get list of all options for DEVICE'''
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
        self.add_argument('-L', '--list-devices', action='store_const', const='list_devices', dest='action', help='show available scanner devices')
        self.add_argument('--format', choices=file_formats, dest='output_format', default='png', help='file format of output file (default: PNG)')
        self.add_argument('-t', '--target-directory', metavar='DIRECTORY', help='output directory (default: an unique, time-based directory is created)')
        self.add_argument('--target-directory-prefix', metavar='PREFIX', help='prefix for directory name if --target-directory is not used')
        self.add_argument('-i', '--icc-profile', metavar='PROFILE', help='include this ICC profile into TIFF file')
        self.add_argument('--accept-md5-only', action='store_true', help='only accept authorization requests using MD5')
        self.add_argument('-n', '--dont-scan', action='store_true', help='(not supported)')
        self.add_argument('-T', '--test', action='store_true', help='(not supported)')
        self.add_argument('-B', '--buffer-size', metavar='#', type=int, default=None, help='input buffer size (in kB; default: 32)')
        self.add_argument('-p', '--progress', action='store_true', help='print progress messages')
        self.add_argument('-v', '--verbose', action='store_true', help='more informational messages')
        self.add_argument('--profile')
        group = self.add_argument_group('batch mode')
        group.add_argument('-b', '--batch-mode', metavar='TEMPLATE', dest='filename_template', help='output filename template (default: p%%04d.<ext>)')
        group.add_argument('--batch-start', metavar='#', default=1, type=int, help='page number to start naming files with (default: 1)')
        group.add_argument('--batch-count', metavar='#', default=infinity, type=int, help='number of pages to scan in a single batch (default: no limit)')
        group.add_argument('--batch-increment', metavar='#', default=1, type=int, help='increase page number in filename by # (default: 1)')
        group.add_argument('--batch-double', action='store_const', dest='batch_increment', const=2, help='same as --batch-increment=2')
        group.add_argument('--batch-prompt', action='store_const', dest='batch_button', const=None, help='wait for ENTER before eatch batch (the default)')
        group.add_argument('--batch-button', metavar='BUTTON', help='wait for the scanner button before each batch')
        group.add_argument('--page-count', metavar='#', default=infinity, type=int, help='total number of pages to scan (default: no limit)')
        group.add_argument('--list-buttons', action='store_const', const='list_buttons', dest='action', help='show available buttons')
        group = self.add_argument_group('XMP support')
        group.add_argument('--xmp', action='store_true', help='create sidecar XMP metadata')
        group.add_argument('--reconstruct-xmp', nargs='+', metavar='IMAGE', help='reconstruct sidecar XMP metadata from existing files (only for advanced users)')
        group.add_argument('--override-xmp', nargs='+', action='append', default=[], metavar='KEY=VALUE', help='override an XMP metadata item (only for advanced users)')
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
        if result.reconstruct_xmp:
            result.action = 'reconstruct_xmp'
        if result.profile is not None:
            my_args = args[1:]
            my_args[:0] = config.get(result.profile)
            my_args[:0] = config.get()
            result, extra_args = self.parse_known_args(my_args)
        result.config = config
        for opt in 'dont-scan', 'test':
            if getattr(result, opt.replace('-', '_')):
                raise self.error('--{0} option is not yet supported'.format(opt))
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
    for d in scanner.get_devices():
        print('\t'.join(d))

def get_device(options):
    scanners = scanner.get_devices()
    if len(scanners) == 0:
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

def get_scanimage_commandline(options, device, start=0, count=infinity, increment=1):
    assert isinstance(device, scanner.Device)
    result = ['scanimage']
    result += ['--device-name', device.name]
    result += ['--format={0}'.format('pnm' if options.output_format == 'pnm' else 'tiff')]
    if options.icc_profile is not None:
        result += ['--icc-profile', options.icc_profile]
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
        raw_input('Press ENTER to continue\n')
        return
    print('Press {0!r} button to continue'.format(button))
    while not device[button]:
        time.sleep(sleep_interval)

def scan_single_batch(options, device, start=0, count=infinity, increment=1):
    assert isinstance(device, scanner.Device)
    device.close()
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
    except ipc.CalledProcessError as ex:
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

class ConvertManager(object):

    def __init__(self, nthreads=None):
        if nthreads is None:
            nthreads = utils.get_cpu_count()
        if nthreads < 1:
            nthreads = 1
        self.queue = queue.Queue(0)
        self.threads = [threading.Thread(target=self._work) for x in xrange(nthreads)]
        for thread in self.threads:
            thread.start()

    def add(self, filename):
        self.queue.put(filename)

    def close(self):
        for thread in self.threads:
            self.queue.put(None)
        qsize = self.queue.qsize()
        if qsize > 0:
            logger.info('Waiting for converter threads to finish ({0})...'.format(
                '~{0} files left'.format(qsize) if qsize > 0
                else '1 file left'
            ))
        for thread in self.threads:
            thread.join()

    def _convert(self, filename):
        logger.debug('Converting %s', filename)
        image = pil.open(filename + temporary_suffix)
        options = {}
        try:
            options['dpi'] = image.info['dpi']
        except LookupError:
            pass
        image.save(filename, **options)
        os.stat(filename)
        os.remove(filename + temporary_suffix)

    def _work(self):
        while True:
            filename = self.queue.get()
            if filename is None:
                return
            self._convert(filename)

def scan(options):
    try:
        device = get_device(options)
    except IndexError as exc:
        error(exc)
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
    increment = options.batch_increment
    batch_count = options.batch_count
    total_count = options.page_count
    convert_manager = ConvertManager()
    try:
        try:
            while total_count > 0:
                wait_for_button(device, options.batch_button)
                for page in scan_single_batch(options, device, start, min(total_count, batch_count), increment):
                    image_filename = gnu.sprintf(options.filename_template, start)
                    if options.xmp:
                        real_image_filename = image_filename
                        if options.output_format not in scanimage_file_formats:
                            real_image_filename += temporary_suffix
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
                    if options.output_format not in scanimage_file_formats:
                        convert_manager.add(image_filename)
                    start += increment
                    total_count -= 1
        except KeyboardInterrupt:
            logger.info('Interrupted by user')
    finally:
        convert_manager.close()

def reconstruct_xmp(options):
    class device:
        vendor = None
        model = None
    if ('device_vendor' in options.override_xmp and 'device_model' in options.override_xmp):
        # Don't bother running get_device(), as it's time consuming.
        pass
    else:
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

def clean_temporary_files(options):
    if options.target_directory is None:
        ArgumentParser().error('--target-directory is obligatory with --clean-temporary-files')
    i = 0
    convert_manager = ConvertManager()
    for root, dirs, files in os.walk(options.target_directory):
        for filename in files:
            filename = os.path.join(root, filename)
            if filename.endswith(temporary_suffix):
                convert_manager.add(filename[:-len(temporary_suffix)])
                i += 1
    convert_manager.close()
    logger.info(
        'No files have been converted' if i == 0
        else '1 file has been converted' if i == 1
        else '{0} files have been converted'.format(i)
    )

def show_config(options):
    tilde = os.path.expanduser('~')
    print('Configuration files:')
    for filename in options.config.get_paths(writable=True):
        if filename.startswith(tilde):
            filename = '~' + filename[len(tilde):]
        print('    {0}'.format(filename))
    extra_options = options.config.get(None)
    print()
    if extra_options:
        print('Default options:')
        print('    {0}'.format(ipc.shell_escape_list(extra_options)))
    else:
        print('No default options')
    i = 0
    for profile in options.config.get_profiles():
        print()
        print('Options for profile {0!r}:'.format(profile))
        extra_options = options.config.get(profile)
        print('    {0}'.format(ipc.shell_escape_list(extra_options)))
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

# vim:ts=4 sts=4 sw=4 et
