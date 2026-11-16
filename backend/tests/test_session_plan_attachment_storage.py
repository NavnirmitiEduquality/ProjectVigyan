
import io
import zipfile

import pytest
from PIL import Image

from app.services.session_plan.attachment_storage import (
    AttachmentValidationError,
    MAX_ATTACHMENT_SIZE_BYTES,
    SessionPlanAttachmentStorage,
)


DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)
PPTX_MIME = (
    "application/vnd.openxmlformats-officedocument."
    "presentationml.presentation"
)


@pytest.fixture
def storage(tmp_path):
    return SessionPlanAttachmentStorage(root=tmp_path / "attachments")


def make_pdf():
    return (
        b"%PDF-1.7\n"
        b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R >>\n"
        b"%%EOF\n"
    )


def make_ooxml(extension):
    output = io.BytesIO()

    if extension == ".docx":
        main_part = "word/document.xml"
        content_type = (
            b"application/vnd.openxmlformats-officedocument."
            b"wordprocessingml.document.main+xml"
        )
        document_xml = (
            b'<?xml version="1.0"?>'
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
            b'wordprocessingml/2006/main"><w:body/></w:document>'
        )
    else:
        main_part = "ppt/presentation.xml"
        content_type = (
            b"application/vnd.openxmlformats-officedocument."
            b"presentationml.presentation.main+xml"
        )
        document_xml = (
            b'<?xml version="1.0"?>'
            b'<p:presentation xmlns:p="http://schemas.openxmlformats.org/'
            b'presentationml/2006/main"/>'
        )

    content_types = (
        b'<?xml version="1.0"?>'
        b'<Types xmlns="http://schemas.openxmlformats.org/'
        b'package/2006/content-types"><Override PartName="/'
        + main_part.encode()
        + b'" ContentType="'
        + content_type
        + b'"/></Types>'
    )

    root_relationships = (
        b'<?xml version="1.0"?>'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/'
        b'package/2006/relationships"/>'
    )

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_relationships)
        archive.writestr(main_part, document_xml)

    return output.getvalue()


def make_image(image_format):
    output = io.BytesIO()
    Image.new("RGB", (2, 2), (120, 80, 40)).save(
        output,
        format=image_format,
    )
    return output.getvalue()


@pytest.mark.parametrize(
    "filename,content_type,data",
    [
        ("lesson.pdf", "application/pdf", make_pdf()),
        ("lesson.docx", DOCX_MIME, make_ooxml(".docx")),
        ("lesson.pptx", PPTX_MIME, make_ooxml(".pptx")),
        ("lesson.jpg", "image/jpeg", make_image("JPEG")),
        ("lesson.jpeg", "image/jpeg", make_image("JPEG")),
        ("lesson.png", "image/png", make_image("PNG")),
    ],
)
def test_valid_attachments_are_accepted(
    storage,
    filename,
    content_type,
    data,
):
    suffix, validated_type = storage.validate(
        filename,
        content_type,
        data,
    )

    assert suffix == "." + filename.rsplit(".", 1)[1].lower()
    assert validated_type == content_type


@pytest.mark.parametrize(
    "filename,content_type,data",
    [
        ("lesson.exe", "application/octet-stream", b"MZtest"),
        ("lesson.pdf", "application/pdf", b"not a PDF"),
        ("lesson.pdf", "image/jpeg", make_pdf()),
        ("lesson.png", "image/png", b"not a PNG"),
        ("lesson.doc", "application/msword", bytes.fromhex("D0CF11E0A1B11AE1") + b"bad"),
        ("lesson.ppt", "application/vnd.ms-powerpoint", bytes.fromhex("D0CF11E0A1B11AE1") + b"bad"),
        ("lesson.docx", DOCX_MIME, b"PK\x03\x04test"),
        ("lesson.pptx", PPTX_MIME, b"PK\x03\x04test"),
    ],
)
def test_invalid_attachments_are_rejected(
    storage,
    filename,
    content_type,
    data,
):
    with pytest.raises(AttachmentValidationError):
        storage.validate(filename, content_type, data)


def test_ooxml_missing_required_part_is_rejected(storage):
    output = io.BytesIO()

    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("_rels/.rels", b"<Relationships/>")

    with pytest.raises(AttachmentValidationError):
        storage.validate("lesson.docx", DOCX_MIME, output.getvalue())


def test_ooxml_duplicate_entries_are_rejected(storage):
    output = io.BytesIO()

    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", b"<Types/>")
        archive.writestr("[Content_Types].xml", b"<Types/>")

    with pytest.raises(AttachmentValidationError):
        storage.validate("lesson.docx", DOCX_MIME, output.getvalue())


def test_empty_attachment_is_rejected(storage):
    with pytest.raises(AttachmentValidationError):
        storage.validate("lesson.pdf", "application/pdf", b"")


def test_attachment_over_five_mib_is_rejected(storage):
    data = b"%PDF-" + b"x" * MAX_ATTACHMENT_SIZE_BYTES

    with pytest.raises(AttachmentValidationError):
        storage.validate("lesson.pdf", "application/pdf", data)


def test_filename_path_components_are_rejected(storage):
    with pytest.raises(AttachmentValidationError):
        storage.validate("../lesson.pdf", "application/pdf", make_pdf())


def test_save_open_and_delete_attachment(storage):
    data = make_pdf()

    key = storage.save("lesson.pdf", "application/pdf", data)

    with storage.open(key) as stored_file:
        assert stored_file.read() == data

    storage.delete(key)

    assert not (storage.root / key).exists()


def test_save_rejects_invalid_content(storage):
    with pytest.raises(AttachmentValidationError):
        storage.save("lesson.pdf", "application/pdf", b"not a PDF")


def test_storage_rejects_path_traversal(storage):
    with pytest.raises(AttachmentValidationError):
        storage.open("../outside.pdf")

    with pytest.raises(AttachmentValidationError):
        storage.delete("../outside.pdf")
