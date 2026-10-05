# SPDX-License-Identifier: Apache-2.0
"""Scoped adapter for python-hwpx 6.3.0's overbroad URI byte replacement.

For documents whose active element/attribute names already use 2011 namespaces,
normalization is unnecessary. Keep all URI-valued attributes/text unchanged.
No raw document/XML writes and no installed package or security-setting edits.
"""
from functools import wraps
from importlib.metadata import version
from zipfile import ZipFile
from unittest.mock import patch
from hwpx.opc import xml_utils
from safe_edit import parse


def preserve_namespace_literals(function):
    @wraps(function)
    def guarded(source,*args,**kwargs):
        if version('python-hwpx')!='6.3.0':raise ValueError('namespace adapter requires validated 6.3.0')
        with ZipFile(source) as archive:
            for member in archive.namelist():
                if not member.endswith(('.xml','.hpf')):continue
                root=parse(archive.read(member))
                for node in root.iter():
                    names=[node.tag,*node.attrib] if isinstance(node.tag,str) else list(node.attrib)
                    if any(name.startswith('{http://www.hancom.co.kr/hwpml/2016/') for name in names):
                        raise ValueError('active 2016 namespace tags/attributes are outside this adapter contract')
        # parse_xml still runs its existing byte/depth/entity/network guards.
        # This isolated, sequential operation bypasses only unnecessary URI
        # substitution; all public document operations and full diffs remain.
        with patch.object(xml_utils,'normalize_hwpml_namespaces',lambda data:data):
            return function(source,*args,**kwargs)
    return guarded
