# SPDX-License-Identifier: Apache-2.0
"""XML 파싱/직렬화를 위한 OPC 공통 유틸리티."""

from __future__ import annotations

from io import BytesIO
from copy import deepcopy
from typing import Mapping

from lxml import etree

from .security import guard_xml_bytes, guard_xml_depth

# Mapping of 2016 HWPML namespace URIs to their 2011 equivalents.
# Documents created with Hancom Office 2016+ may use these newer URIs.
# Normalising to 2011 at parse time lets the rest of the codebase use a
# single set of namespace constants without any lookup changes.
_HWPML_2016_TO_2011: tuple[tuple[bytes, bytes], ...] = (
    (b"http://www.hancom.co.kr/hwpml/2016/paragraph", b"http://www.hancom.co.kr/hwpml/2011/paragraph"),
    (b"http://www.hancom.co.kr/hwpml/2016/head", b"http://www.hancom.co.kr/hwpml/2011/head"),
    (b"http://www.hancom.co.kr/hwpml/2016/section", b"http://www.hancom.co.kr/hwpml/2011/section"),
    (b"http://www.hancom.co.kr/hwpml/2016/core", b"http://www.hancom.co.kr/hwpml/2011/core"),
    (b"http://www.hancom.co.kr/hwpml/2016/master-page", b"http://www.hancom.co.kr/hwpml/2011/master-page"),
    (b"http://www.hancom.co.kr/hwpml/2016/history", b"http://www.hancom.co.kr/hwpml/2011/history"),
    (b"http://www.hancom.co.kr/hwpml/2016/app", b"http://www.hancom.co.kr/hwpml/2011/app"),
)


def normalize_hwpml_namespaces(data: bytes) -> bytes:
    """Normalize namespace bindings and QNames, preserving XML data values.

    Candidate correction: hp:required-namespace and ordinary attribute/text
    values must retain their original URIs. Global byte replacement can
    silently change conditional-format behavior on a later native save.
    """
    if not any(old in data for old, _ in _HWPML_2016_TO_2011):
        return data
    # URI-valued attributes (notably hp:required-namespace), visible text,
    # comments and CDATA are data, not namespace bindings. Global replacement
    # changes conditional-format semantics, even when current PDF is identical.
    guard_xml_bytes(data)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    tree = etree.parse(BytesIO(data), parser=parser)
    original = tree.getroot()
    guard_xml_depth(original)
    mapping = {old.decode(): new.decode() for old, new in _HWPML_2016_TO_2011}

    def qname(value: str) -> str:
        if value.startswith('{'):
            uri, name = value[1:].split('}', 1)
            return '{' + mapping.get(uri, uri) + '}' + name
        return value

    def rebuild(element: etree._Element) -> etree._Element:
        if not isinstance(element.tag, str):
            return deepcopy(element)
        result = etree.Element(qname(element.tag), nsmap={key: mapping.get(uri, uri) for key, uri in element.nsmap.items()})
        for key, value in element.attrib.items():
            result.set(qname(key), value)
        result.text, result.tail = element.text, element.tail
        for child in element:
            result.append(rebuild(child))
        return result

    before, after = [], []
    cursor = original.getprevious()
    while cursor is not None:
        before.append(deepcopy(cursor));cursor = cursor.getprevious()
    cursor = original.getnext()
    while cursor is not None:
        after.append(deepcopy(cursor));cursor = cursor.getnext()
    normalized = rebuild(original)
    for sibling in reversed(before):normalized.addprevious(sibling)
    for sibling in reversed(after):normalized.addnext(sibling)
    declaration = data.lstrip().startswith(b'<?xml')
    return etree.tostring(normalized.getroottree(), encoding='utf-8', xml_declaration=declaration)


def parse_xml(data: bytes) -> etree._Element:
    """바이트 XML 문서를 파싱해 루트 요소를 반환한다.

    2016 HWPML 네임스페이스는 파싱 전에 2011 버전으로 자동 정규화된다.
    """

    guard_xml_bytes(data)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    root = etree.fromstring(normalize_hwpml_namespaces(data), parser=parser)
    guard_xml_depth(root)
    return root


def parse_xml_with_namespaces(data: bytes) -> tuple[etree._Element, Mapping[str, str]]:
    """루트 요소와 네임스페이스 매핑(prefix -> uri)을 함께 반환한다."""

    root = parse_xml(data)
    namespaces = {"" if prefix is None else prefix: uri for prefix, uri in root.nsmap.items() if uri}
    return root, namespaces


def iter_declared_namespaces(data: bytes) -> Mapping[str, str]:
    """XML 선언 순서를 보존한 네임스페이스 매핑을 추출한다.

    2016 HWPML 네임스페이스는 2011 버전으로 정규화된다.
    """

    guard_xml_bytes(data)
    normalized = normalize_hwpml_namespaces(data)
    namespaces: dict[str, str] = {}
    for _, elem in etree.iterparse(
        BytesIO(normalized),
        events=("start-ns",),
        resolve_entities=False,
        no_network=True,
        huge_tree=False,
    ):
        prefix, uri = elem
        namespaces[prefix or ""] = uri
    return namespaces


def extract_xml_declaration(data: bytes) -> bytes | None:
    """문서 상단의 XML 선언(`<?xml ... ?>`)을 추출한다."""

    stripped = data.lstrip()
    if not stripped.startswith(b"<?xml"):
        return None
    end = stripped.find(b"?>")
    if end == -1:
        return None
    return stripped[: end + 2]


def serialize_xml(element: etree._Element, *, xml_declaration: bool = False) -> bytes:
    """요소를 UTF-8 XML 바이트로 직렬화한다."""

    return etree.tostring(element, encoding="utf-8", xml_declaration=xml_declaration)
