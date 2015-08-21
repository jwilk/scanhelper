# encoding=UTF-8

# Copyright © 2012-2015 Jakub Wilk <jwilk@jwilk.net>
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

import datetime
import os
import re
import time
import uuid
import xml.dom.minidom as minidom

from . import utils

try:
    import PIL.Image as pil
except ImportError as ex:
    utils.enhance_import_error(ex, 'Python Imaging Library', 'python-imaging', 'http://www.pythonware.com/products/pil/')
    raise

try:
    import jinja2
except ImportError as ex:
    utils.enhance_import_error(ex, 'Jinja2 templating library', 'python-jinja2', 'http://jinja.pocoo.org/')
    raise

from . import __version__

documented_template = '''\
<x:xmpmeta
    xmlns:x="adobe:ns:meta/"
    xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:tiff="http://ns.adobe.com/tiff/1.0/"
    xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"
    xmlns:stEvt="http://ns.adobe.com/xap/1.0/sType/ResourceEvent#"
>
<rdf:RDF>
    <rdf:Description rdf:about="">
        <xmp:CreatorTool>scanhelper {{version}}</xmp:CreatorTool> # version of scanhelper
        <xmp:CreateDate>{{image_timestamp}}</xmp:CreateDate> # image creation date (e.g. ``2005-09-07T15:01:43-07:00``)
        <xmp:MetadataDate>{{metadata_timestamp}}</xmp:MetadataDate> # metadata creation date (e.g. ``2005-09-07T15:01:43-07:00``)
        <dc:format>{{media_type}}</dc:format> # media type (e.g. ``image/png``)
{% if device_vendor %}\
        <tiff:Make>{{device_vendor}}</tiff:Make> # scanner vendor
{% endif %}\
{% if device_model %}\
        <tiff:Model>{{device_model}}</tiff:Model> # scanner model
{% endif %}\
        <tiff:ImageWidth>{{width}}</tiff:ImageWidth> # image width, in pixels
        <tiff:ImageHeight>{{height}}</tiff:ImageHeight> # image height, in pixels
{% if dpi %}\
        <tiff:XResolution>{{dpi}}/1</tiff:XResolution> # image resolution, in dots per inch
        <tiff:YResolution>{{dpi}}/1</tiff:YResolution>
        <tiff:ResolutionUnit>2</tiff:ResolutionUnit>
{% endif %}\
        <xmpMM:DocumentID>{{document_id}}</xmpMM:DocumentID>
        <xmpMM:InstanceID>{{instance_id}}</xmpMM:InstanceID>
        <xmpMM:History>
            <rdf:Seq>
                <rdf:li rdf:parseType="Resource">
                    <stEvt:action>created</stEvt:action>
                    <stEvt:softwareAgent>scanhelper {{version}}</stEvt:softwareAgent>
                    <stEvt:when>{{image_timestamp}}</stEvt:when>
                    <stEvt:instanceID>{{instance_id}}</stEvt:instanceID>
                </rdf:li>
            </rdf:Seq>
        </xmpMM:History>
    </rdf:Description>
</rdf:RDF>
</x:xmpmeta>

'''

def _extend_doc():
    global __doc__
    documentation = re.findall('{{(\w+)}}.*\s+#\s+(.*)', documented_template)
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
    for key, description in documentation:
        __doc__ += line_fmt.format(key=key, description=description)
    __doc__ += separator

_extend_doc()
del _extend_doc

template = jinja2.Template(re.sub('\s+#\s+.*', '', documented_template))

media_types = dict(
    PPM='image/x-portable-anymap',
    PNG='image/png',
    TIFF='image/tiff',
)

class rfc3339(object):

    def __init__(self, unixtime):
        self._localtime = time.localtime(unixtime)
        self._tzdelta = (
            datetime.datetime.fromtimestamp(unixtime) -
            datetime.datetime.utcfromtimestamp(unixtime)
        )

    def _str(self):
        return time.strftime('%Y-%m-%dT%H:%M:%S', self._localtime)

    def _str_tz(self):
        offset = self._tzdelta.days * 3600 * 24 + self._tzdelta.seconds
        hours, minutes = divmod(abs(offset) // 60, 60)
        sign = '+' if offset >= 0 else '-'
        return '{s}{h:02}:{m:02}'.format(s=sign, h=hours, m=minutes)

    def __str__(self):
        '''Format the timestamp object in accordance with RFC 3339.'''
        return self._str() + self._str_tz()

def mtime(filename):
    return rfc3339(os.stat(filename).st_mtime)

def now():
    return rfc3339(time.time())

def gen_uuid():
    '''
    generate an UUID URN, in accordance with RFC 4122
    '''
    # https://tools.ietf.org/html/rfc4122#section-3
    return 'urn:uuid:{uuid}'.format(uuid=uuid.uuid4())

def write(xmp_file, image_filename, device, override):
    image_timestamp = mtime(image_filename)
    metadata_timestamp = now()
    image = pil.open(image_filename)
    width, height = image.size
    try:
        x_dpi, y_dpi = image.info['dpi']
        dpi = max(x_dpi, y_dpi)
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
        document_id=gen_uuid(),
        instance_id=gen_uuid(),
    )
    parameters.update(override)
    xmp_data = template.render(**parameters).encode('UTF-8')
    assert minidom.parseString(xmp_data)
    xmp_file.write(xmp_data.encode('UTF-8'))

__all__ = ['write']

# vim:ts=4 sts=4 sw=4 et
