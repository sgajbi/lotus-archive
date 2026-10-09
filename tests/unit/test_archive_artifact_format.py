from io import BytesIO
from zipfile import ZipFile

import pytest

from app.archive.artifact_format import XLSX_MIME, validate_artifact_format
from app.archive.exceptions import MetadataValidationError
from tests.fixtures.composite_workbook import workbook_bytes
import app.archive.artifact_format as artifact_format


@pytest.mark.parametrize("limit", ["MAX_XLSX_PARTS", "MAX_XLSX_EXPANDED_BYTES"])
def test_package_limits(limit: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as context:
        context.setattr(artifact_format, limit, 1)
        with pytest.raises(MetadataValidationError):
            validate_artifact_format(
                output_format="xlsx", mime_type=XLSX_MIME, content=workbook_bytes()
            )
    validate_artifact_format(output_format="xlsx", mime_type=XLSX_MIME, content=workbook_bytes())


@pytest.mark.parametrize(
    "part,content",
    [
        ("xl/workbook.xml", '<!DOCTYPE a [<!ENTITY x "bad">]><a/>'),
        ("xl/workbook.xml", "<workbook/>"),
        (
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
        ),
        (
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="x" Type="anything" Target="https://example.com" TargetMode="External"/></Relationships>',
        ),
    ],
)
def test_invalid_xml_or_relationships_refused(part: str, content: str) -> None:
    output = BytesIO()
    with ZipFile(BytesIO(workbook_bytes())) as source, ZipFile(output, "w") as target:
        for item in source.infolist():
            target.writestr(item, content if item.filename == part else source.read(item))
    with pytest.raises(MetadataValidationError):
        validate_artifact_format(
            output_format="xlsx", mime_type=XLSX_MIME, content=output.getvalue()
        )


@pytest.mark.parametrize("name", ["../outside.xml", "/outside.xml", "xl/workbook.xml"])
def test_unsafe_or_duplicate_zip_parts_refused(name: str) -> None:
    output = BytesIO()
    with ZipFile(BytesIO(workbook_bytes())) as source, ZipFile(output, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item))
        if name == "xl/workbook.xml":
            with pytest.warns(UserWarning, match="Duplicate name"):
                target.writestr(name, "untrusted")
        else:
            target.writestr(name, "untrusted")
    with pytest.raises(MetadataValidationError):
        validate_artifact_format(
            output_format="xlsx", mime_type=XLSX_MIME, content=output.getvalue()
        )


def test_encrypted_zip_claim_refused() -> None:
    content = bytearray(workbook_bytes())
    central = content.index(b"PK\x01\x02")
    content[central + 8] |= 1
    with pytest.raises(MetadataValidationError):
        validate_artifact_format(output_format="xlsx", mime_type=XLSX_MIME, content=bytes(content))


def test_utf16_entity_declaration_refused_before_expansion() -> None:
    output = BytesIO()
    xml = '<!DOCTYPE workbook [<!ENTITY x "injected">]><workbook>&x;</workbook>'.encode("utf-16")
    with ZipFile(BytesIO(workbook_bytes())) as source, ZipFile(output, "w") as target:
        for item in source.infolist():
            target.writestr(item, xml if item.filename == "xl/workbook.xml" else source.read(item))
    with pytest.raises(MetadataValidationError):
        validate_artifact_format(
            output_format="xlsx", mime_type=XLSX_MIME, content=output.getvalue()
        )


@pytest.mark.parametrize(
    "part,before,after",
    [
        (
            "[Content_Types].xml",
            "spreadsheetml.sheet.main+xml",
            "ms-excel.sheet.macroEnabled.main+xml",
        ),
        ("_rels/.rels", "relationships/officeDocument", "relationships/unrelated"),
        ("xl/workbook.xml", "sheets>", "other>"),
        ("xl/worksheets/sheet1.xml", "worksheet", "wrongroot"),
        ("xl/_rels/workbook.xml.rels", "relationships/worksheet", "relationships/unrelated"),
        (
            "xl/_rels/workbook.xml.rels",
            "</Relationships>",
            '<Relationship Id="rId1" Type="duplicate" Target="duplicate"/></Relationships>',
        ),
    ],
)
def test_mislabelled_or_ambiguous_ooxml_refused(part: str, before: str, after: str) -> None:
    output = BytesIO()
    with ZipFile(BytesIO(workbook_bytes())) as source, ZipFile(output, "w") as target:
        for item in source.infolist():
            content = source.read(item)
            if item.filename == part:
                content = content.replace(before.encode(), after.encode())
            target.writestr(item, content)
    with pytest.raises(MetadataValidationError):
        validate_artifact_format(
            output_format="xlsx", mime_type=XLSX_MIME, content=output.getvalue()
        )


def test_real_workbook_and_existing_pdf_are_admitted() -> None:
    validate_artifact_format(output_format="xlsx", mime_type=XLSX_MIME, content=workbook_bytes())
    validate_artifact_format(output_format="pdf", mime_type="application/pdf", content=b"pdf")


@pytest.mark.parametrize("content", [b"", b"%PDF-1.4", b"PK fake workbook", b"not a zip"])
def test_non_workbooks_refused(content: bytes) -> None:
    with pytest.raises(MetadataValidationError):
        validate_artifact_format(output_format="xlsx", mime_type=XLSX_MIME, content=content)


@pytest.mark.parametrize("format,mime", [("xlsx", "application/pdf"), ("pdf", XLSX_MIME)])
def test_format_media_type_disagreement_refused(format: str, mime: str) -> None:
    with pytest.raises(MetadataValidationError):
        validate_artifact_format(output_format=format, mime_type=mime, content=workbook_bytes())


@pytest.mark.parametrize(
    "removed", ["[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"]
)
def test_incomplete_packages_refused(removed: str) -> None:
    output = BytesIO()
    with ZipFile(BytesIO(workbook_bytes())) as source, ZipFile(output, "w") as target:
        for part in source.infolist():
            if part.filename != removed:
                target.writestr(part, source.read(part))
    with pytest.raises(MetadataValidationError):
        validate_artifact_format(
            output_format="xlsx", mime_type=XLSX_MIME, content=output.getvalue()
        )
