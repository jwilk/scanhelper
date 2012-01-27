# encoding=UTF-8

# Copyright © 2012 Jakub Wilk <jwilk@jwilk.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 2 dated June, 1991.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.

'''
For scanhelper ≥ 0.2, you can use the ``--xmp`` option to generate XMP_
metadata for each scanned image in a separate file (so called *sidecar XMP
file*).

It is also possible to reconstruct XMP metadata for existing files using the
``--reconstruct-xmp`` option. However, scanhelper is not always able to extract
all the needed information correctly (e.g. old versions of scanhelper didn't
preserve information about resolution). To work around this problem, there is
``--override-xmp KEY=VALUE ...`` option that allows you to override some
metadata items.
'''

import os
import re
import datetime

try:
    import Image as pil
except ImportError, ex:
    utils.enhance_import_error(ex, 'Python Imaging Library', 'python-imaging', 'http://www.pythonware.com/products/pil/')
    raise

try:
    import jinja2
except ImportError, ex:
    utils.enhance_import_error(ex, 'Jinja2 templating library', 'python-jinja2', 'http://jinja.pocoo.org/docs/')
    raise

from . import __version__

documented_template = '''\
<rdf:RDF
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:tiff="http://ns.adobe.com/tiff/1.0/"
>
    <rdf:Description rdf:about="">
        <xmp:CreatorTool>scanhelper {{version}}</xmp:CreatorTool> # version of scanhelper
        <xmp:CreateDate>{{image_timestamp}}</xmp:CreateDate> # image creation date (e.g. ``2005-09-07T15:01:43-07:00``)
        <xmp:MetadataDate>{{metadata_timestamp}}</xmp:MetadataDate> # metadata creation date (e.g. ``2005-09-07T15:01:43-07:00``)
        <dc:format>{{media_type}}</dc:format> # media type (e.g. ``image/png``)
        <tiff:Make>{{device_vendor}}</tiff:Make> # scanner vendor
        <tiff:Model>{{device_model}}</tiff:Model> # scanner model
        <tiff:ImageWidth>{{width}}</tiff:ImageWidth> # image width, in pixels
        <tiff:ImageHeight>{{height}}</tiff:ImageHeight> # image height, in pixels
{% if dpi %}\
        <tiff:XResolution>{{dpi}}/1</tiff:XResolution> # image resolution, in dots per inch
        <tiff:YResolution>{{dpi}}/1</tiff:YResolution>
        <tiff:ResolutionUnit>2</tiff:ResolutionUnit>
{% endif %}\
    </rdf:Description>
</rdf:RDF>
'''

def _extend_doc():
    global __doc__
    documentation = re.findall('{{(\w+)}}.*#\s*(.*)', documented_template)
    key_maxlen = max(len(key) for key, _ in documentation)
    descr_maxlen = max(len(descr) for _, descr in documentation)
    separator = ('=' * (key_maxlen)) + ' ' + ('=' * (descr_maxlen)) + '\n'
    line_fmt = '{key:N} {description}\n'.replace('N', str(key_maxlen))
    __doc__ += '\nList of available metadata keys:\n'
    __doc__ += separator
    __doc__ += line_fmt.format(
        key='key'.center(key_maxlen),
        description='description'.center(descr_maxlen)
    )
    __doc__ += separator
    for key, description in re.findall('{{(\w+)}}.*#\s*(.*)', documented_template):
        __doc__ += line_fmt.format(key=key, description=description)
    __doc__ += separator

_extend_doc()
del _extend_doc

template = jinja2.Template(re.sub('\s*#.*', '', documented_template))

media_types = dict(
    PPM='image/x-portable-anymap',
    PNG='image/png',
    TIFF='image/png',
)

def rfc3339(timestamp):
    return timestamp.strftime('%Y-%m-%dT%H:%M:%S') + '+00:00'

def mtime(filename):
    unix_timestamp = os.stat(filename).st_mtime
    return datetime.datetime.utcfromtimestamp(unix_timestamp)

def now():
    return datetime.datetime.utcnow()

def write(xmp_file, image_filename, device, override):
    image_timestamp = rfc3339(mtime(image_filename))
    metadata_timestamp = rfc3339(now())
    image = pil.open(image_filename)
    width, height = image.size
    try:
        dpi = image.info['dpi']
    except LookupError:
        dpi = None
    media_type = media_types[image.format]
    parameters = dict(
        version=__version__,
        device_vendor=device.vendor,
        device_model=device.model,
        image_timestamp=image_timestamp,
        metadata_timestamp=metadata_timestamp,
        media_type=media_type,
        device=device,
        width=width, height=height,
        dpi=dpi,
    )
    parameters.update(override)
    xmp_data = template.render(**parameters)
    xmp_file.write(xmp_data.encode('UTF-8'))

# vim:ts=4 sw=4 et
