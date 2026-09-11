from markitdown.twoways import (
    Canvas,
    DocumentIR,
    DocumentMetadata,
    EditOperation,
    EditPrecondition,
    Geometry,
    ImagePayload,
    NativeLocator,
    NativePayload,
    Node,
    Paragraph,
    Provenance,
    Resource,
    Style,
    TableCell,
    TablePayload,
    TextPayload,
    TextRun,
    UnknownNativePayload,
)


def make_representative_document(title: str = "Quarterly Revenue") -> DocumentIR:
    title_style = Style(direct={"font_size": 28, "bold": True})
    text_payload = TextPayload(
        text="Revenue increased 38%",
        paragraphs=(
            Paragraph(
                runs=(
                    TextRun("Revenue increased "),
                    TextRun("38%", style=Style(direct={"bold": True})),
                ),
            ),
        ),
    )
    nodes = {
        "group1": Node(
            node_id="group1",
            kind="group",
            canvas_id="slide1",
            children=("text1", "image1"),
            order=0,
            geometry=Geometry(x=0, y=0, width=10, height=7.5, unit="in"),
        ),
        "text1": Node(
            node_id="text1",
            kind="text",
            semantic_role="title",
            parent_id="group1",
            canvas_id="slide1",
            order=0,
            style=title_style,
            geometry=Geometry(
                x=914400, y=457200, width=4572000, height=685800, unit="emu"
            ),
            provenance=(
                Provenance(
                    source_format="pptx",
                    canvas_index=0,
                    part_uri="/ppt/slides/slide1.xml",
                ),
            ),
            native_locator=NativeLocator(
                backend="ooxml",
                part_uri="/ppt/slides/slide1.xml",
                object_id="17",
                creation_id="shape-title-1",
            ),
            payload=text_payload,
        ),
        "image1": Node(
            node_id="image1",
            kind="image",
            parent_id="group1",
            canvas_id="slide1",
            order=1,
            geometry=Geometry(x=6, y=1.5, width=3, height=3, unit="in"),
            payload=ImagePayload(resource_id="img1", alt_text="Revenue chart"),
        ),
        "table1": Node(
            node_id="table1",
            kind="table",
            canvas_id="slide2",
            order=0,
            payload=TablePayload(
                rows=1,
                columns=2,
                cells=(
                    TableCell(row=0, column=0, text="Region"),
                    TableCell(row=0, column=1, text="Revenue"),
                ),
            ),
        ),
        "unknown1": Node(
            node_id="unknown1",
            kind="unknown_native",
            canvas_id="slide2",
            order=1,
            payload=UnknownNativePayload(native_payload_ref="native1"),
        ),
    }
    return DocumentIR(
        document_id="doc1",
        metadata=DocumentMetadata(title=title, author="Nolane"),
        canvases=(
            Canvas(
                canvas_id="slide1",
                index=0,
                kind="slide",
                width=13.333,
                height=7.5,
                unit="in",
                root_node_ids=("group1",),
            ),
            Canvas(
                canvas_id="slide2",
                index=1,
                kind="slide",
                width=13.333,
                height=7.5,
                unit="in",
                root_node_ids=("table1", "unknown1"),
            ),
        ),
        nodes=nodes,
        root_node_ids=("group1", "table1", "unknown1"),
        resources={
            "img1": Resource(
                resource_id="img1",
                sha256="a" * 64,
                content_type="image/png",
                filename="chart.png",
                size_bytes=1234,
                storage_ref="assets/aa.png",
            )
        },
        native_payloads={
            "native1": NativePayload(
                payload_id="native1",
                backend="ooxml",
                content_type="application/xml",
                sha256="b" * 64,
                storage_ref="native/unknown1.xml",
                scope="node",
            )
        },
        edits=(
            EditOperation(
                operation_id="edit1",
                type="replace_text",
                target_node_id="text1",
                precondition=EditPrecondition(
                    expected_old_value="Revenue increased 38%"
                ),
                payload={"text": "Revenue increased 42%"},
                source_label="identity-markdown",
            ),
            EditOperation(
                operation_id="edit2",
                type="move_resize",
                target_node_id="image1",
                payload={"x": 6.1, "y": 1.5, "width": 3.1, "height": 3.0, "unit": "in"},
            ),
        ),
    )
