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

import os
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

template = jinja2.Template('''\
<rdf:RDF
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:tiff="http://ns.adobe.com/tiff/1.0/"
>
    <rdf:Description rdf:about="">
        <xmp:CreatorTool>scanhelper {{version}}</xmp:CreatorTool>
        <xmp:CreateDate>{{image_timestamp}}</xmp:CreateDate>
        <xmp:MetadataDate>{{metadata_timestamp}}</xmp:MetadataDate>
        <dc:format>{{media_type}}</dc:format>
        <tiff:Make>{{device_vendor}}</tiff:Make>
        <tiff:Model>{{device_model}}</tiff:Model>
        <tiff:ImageWidth>{{width}}</tiff:ImageWidth>
        <tiff:ImageHeight>{{height}}</tiff:ImageHeight>
{% if dpi %}\
        <tiff:XResolution>{{dpi}}/1</tiff:XResolution>
        <tiff:YResolution>{{dpi}}/1</tiff:YResolution>
        <tiff:ResolutionUnit>2</tiff:ResolutionUnit>
{% endif %}\
    </rdf:Description>
</rdf:RDF>
''')

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

def write(xmp_file, image_filename, device, **override):
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
