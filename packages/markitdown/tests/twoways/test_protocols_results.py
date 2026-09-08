from io import BytesIO

import pytest

from markitdown.twoways import (
    DocumentIRReader,
    DocumentWriter,
    FidelityEvidence,
    FidelityReport,
    FidelityStatus,
    TargetInfo,
    WriterResult,
)
from ._fixtures import make_representative_document


class FakeReader:
    def accepts(self, file_stream, stream_info, **kwargs):
        position = file_stream.tell()
        file_stream.read(1)
        file_stream.seek(position)
        return True

    def read(self, file_stream, stream_info, **kwargs):
        return make_representative_document()


class FakeWriter:
    def accepts(self, document, target, **kwargs):
        return target.format == "pptx"

    def write(self, document, output, target, **kwargs):
        output.write(b"pptx")
        return WriterResult(
            format="pptx",
            mode="patch",
            bytes_written=4,
            fidelity=FidelityReport(claimed_tier="high"),
            unsupported_operations=("rotate_3d",),
        )


def test_reader_protocol_and_accepts_stream_position_fixture():
    reader = FakeReader()
    assert isinstance(reader, DocumentIRReader)
    stream = BytesIO(b"abc")
    assert reader.accepts(stream, object()) is True
    assert stream.tell() == 0


def test_writer_protocol_target_and_result_plumbing():
    writer = FakeWriter()
    assert isinstance(writer, DocumentWriter)
    doc = make_representative_document()
    target = TargetInfo(format="pptx", extension=".pptx")
    assert writer.accepts(doc, target)
    output = BytesIO()
    result = writer.write(doc, output, target)
    assert output.getvalue() == b"pptx"
    assert result.bytes_written == 4
    assert result.unsupported_operations == ("rotate_3d",)


def test_exact_preserve_cannot_claim_failed_required_evidence():
    evidence = FidelityEvidence(
        check_code="ooxml.untouched_parts",
        status=FidelityStatus.FAILED,
        description="untouched parts changed",
        required=True,
    )
    with pytest.raises(ValueError, match="exact-preserve"):
        FidelityReport(claimed_tier="exact-preserve", evidence=(evidence,))


def test_exact_preserve_allows_failed_optional_evidence():
    evidence = FidelityEvidence(
        check_code="visual.preview",
        status="failed",
        description="preview unavailable",
        required=False,
    )
    report = FidelityReport(claimed_tier="exact-preserve", evidence=(evidence,))
    assert report.evidence[0].status is FidelityStatus.FAILED


def test_target_info_requires_non_empty_format():
    with pytest.raises(ValueError, match="format"):
        TargetInfo(format="")
