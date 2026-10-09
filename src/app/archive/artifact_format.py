"""Bounded binary-format admission before storage or idempotent replay."""

from io import BytesIO
from base64 import b64decode
from binascii import Error as Base64DecodeError
from posixpath import normpath
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree
from zlib import error as ZipCompressionError

from app.archive.exceptions import MetadataValidationError

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_XLSX_PARTS = 4096
MAX_XLSX_EXPANDED_BYTES = 128 * 1024 * 1024
_MAIN_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
_SHEET_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
_CONTENT_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
_SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def decode_document_content(content_base64: str, max_decoded_bytes: int) -> bytes:
    try:
        content = b64decode(content_base64, validate=True)
    except Base64DecodeError as exc:
        raise MetadataValidationError("document content must be valid base64") from exc
    if len(content) > max_decoded_bytes:
        raise MetadataValidationError("document content exceeds configured archive size limit")
    return content


def validate_artifact_format(*, output_format: str, mime_type: str, content: bytes) -> None:
    """Preserve existing families; XLSX claims require an actual OOXML workbook."""
    if output_format != "xlsx" and mime_type != XLSX_MIME:
        return
    if output_format != "xlsx" or mime_type != XLSX_MIME:
        raise MetadataValidationError("XLSX format and media type must agree")
    try:
        with ZipFile(BytesIO(content)) as package:
            _validate_package_bounds(package)
            _validate_workbook(package)
    except (
        BadZipFile,
        KeyError,
        ValueError,
        ElementTree.ParseError,
        RuntimeError,
        EOFError,
        ZipCompressionError,
    ) as exc:
        raise MetadataValidationError("document content is not a bounded XLSX workbook") from exc


def _validate_package_bounds(package: ZipFile) -> None:
    parts = package.infolist()
    names = [part.filename for part in parts]
    if len(parts) > MAX_XLSX_PARTS or len(names) != len(set(names)):
        raise ValueError("unbounded or ambiguous workbook package")
    if sum(part.file_size for part in parts) > MAX_XLSX_EXPANDED_BYTES:
        raise ValueError("expanded workbook exceeds size bound")
    if any(part.flag_bits & 1 for part in parts):
        raise ValueError("encrypted workbook is not admitted")
    if any(name.startswith("/") or ".." in name.split("/") for name in names):
        raise ValueError("unsafe workbook part path")


def _validate_workbook(package: ZipFile) -> None:
    types = _xml(package.read("[Content_Types].xml"))
    overrides = {
        node.attrib.get("PartName"): node.attrib.get("ContentType")
        for node in types.findall(f"{_CONTENT_NS}Override")
    }
    if overrides.get("/xl/workbook.xml") != _MAIN_TYPE:
        raise ValueError("workbook content type is not XLSX")
    root_links = _relationships(package, "_rels/.rels")
    if not any(
        kind == f"{_DOC_REL_NS}/officeDocument" and target == "xl/workbook.xml"
        for kind, target in root_links.values()
    ):
        raise ValueError("package lacks workbook relationship")
    workbook = _xml(package.read("xl/workbook.xml"))
    if workbook.tag != f"{_SHEET_NS}workbook":
        raise ValueError("workbook root is invalid")
    sheets = workbook.findall(f"{_SHEET_NS}sheets/{_SHEET_NS}sheet")
    if not sheets:
        raise ValueError("workbook requires worksheet evidence")
    links = _relationships(package, "xl/_rels/workbook.xml.rels")
    for sheet in sheets:
        kind, target = links[sheet.attrib[f"{{{_DOC_REL_NS}}}id"]]
        part = normpath(f"xl/{target}") if not target.startswith("/") else target.lstrip("/")
        if kind != f"{_DOC_REL_NS}/worksheet" or overrides.get(f"/{part}") != _SHEET_TYPE:
            raise ValueError("worksheet relationship is invalid")
        if _xml(package.read(part)).tag != f"{_SHEET_NS}worksheet":
            raise ValueError("worksheet part is invalid")


def _relationships(package: ZipFile, name: str) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for node in _xml(package.read(name)).findall(f"{_REL_NS}Relationship"):
        if node.attrib.get("TargetMode") == "External":
            raise ValueError("external workbook relationships are not admitted")
        identifier = node.attrib["Id"]
        if identifier in result:
            raise ValueError("ambiguous workbook relationships")
        result[identifier] = (node.attrib["Type"], node.attrib["Target"])
    return result


def _xml(content: bytes) -> ElementTree.Element:
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ValueError("XML declarations are not permitted")
    return ElementTree.fromstring(content, parser=ElementTree.XMLParser(target=_NoDeclarations()))


class _NoDeclarations(ElementTree.TreeBuilder):
    def doctype(self, _name: str, _public_id: str | None, _system_id: str | None) -> None:
        raise ValueError("XML declarations are not permitted")
