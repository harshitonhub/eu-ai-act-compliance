from unittest.mock import MagicMock, patch

import pytest

from src.evidence.file_ingestion import MAX_FILE_SIZE_BYTES, FileValidationError, extract_evidence_text


def test_extracts_valid_txt():
    text = extract_evidence_text(filename="policy.txt", content=b"Our risk management policy...")
    assert text == "Our risk management policy..."


def test_rejects_invalid_utf8_txt():
    with pytest.raises(FileValidationError, match="UTF-8"):
        extract_evidence_text(filename="policy.txt", content=b"\xff\xfe\x00\x01")


def test_rejects_empty_file():
    with pytest.raises(FileValidationError, match="empty"):
        extract_evidence_text(filename="policy.txt", content=b"")


def test_rejects_oversized_file():
    oversized = b"a" * (MAX_FILE_SIZE_BYTES + 1)
    with pytest.raises(FileValidationError, match="exceeds"):
        extract_evidence_text(filename="policy.txt", content=oversized)


def test_rejects_disallowed_extension():
    with pytest.raises(FileValidationError, match="not allowed"):
        extract_evidence_text(filename="policy.exe", content=b"whatever")


def test_extracts_valid_pdf_with_mocked_reader():
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "Risk management policy text."
    with patch("src.evidence.file_ingestion.pypdf.PdfReader") as mock_reader:
        mock_reader.return_value.pages = [fake_page]
        text = extract_evidence_text(filename="policy.pdf", content=b"%PDF-fake-bytes")

    assert text == "Risk management policy text."


def test_pdf_with_no_extractable_text_is_rejected():
    fake_page = MagicMock()
    fake_page.extract_text.return_value = ""
    with patch("src.evidence.file_ingestion.pypdf.PdfReader") as mock_reader:
        mock_reader.return_value.pages = [fake_page]
        with pytest.raises(FileValidationError, match="no extractable text"):
            extract_evidence_text(filename="policy.pdf", content=b"%PDF-fake-bytes")


def test_corrupt_pdf_is_rejected():
    with pytest.raises(FileValidationError, match="Could not parse PDF"):
        extract_evidence_text(filename="policy.pdf", content=b"this is not a real pdf")


def test_extracts_valid_docx_with_mocked_document():
    fake_paragraph = MagicMock()
    fake_paragraph.text = "Risk management policy text."
    with patch("src.evidence.file_ingestion.Document") as mock_document:
        mock_document.return_value.paragraphs = [fake_paragraph]
        text = extract_evidence_text(filename="policy.docx", content=b"fake-docx-bytes")

    assert text == "Risk management policy text."


def test_docx_with_no_extractable_text_is_rejected():
    with patch("src.evidence.file_ingestion.Document") as mock_document:
        mock_document.return_value.paragraphs = []
        with pytest.raises(FileValidationError, match="no extractable text"):
            extract_evidence_text(filename="policy.docx", content=b"fake-docx-bytes")


def test_corrupt_docx_is_rejected():
    with pytest.raises(FileValidationError, match="Could not parse DOCX"):
        extract_evidence_text(filename="policy.docx", content=b"this is not a real docx")
