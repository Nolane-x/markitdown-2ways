from io import BytesIO

from markitdown._stream_info import StreamInfo
from markitdown.converters._csv_converter import CsvConverter


def test_existing_one_way_csv_converter_output_is_unchanged() -> None:
    result = CsvConverter().convert(
        BytesIO(b"name,city\nAda,North\n"),
        StreamInfo(extension=".csv", mimetype="text/csv", charset="utf-8"),
    )

    assert result.markdown == ("| name | city |\n" "| --- | --- |\n" "| Ada | North |")
