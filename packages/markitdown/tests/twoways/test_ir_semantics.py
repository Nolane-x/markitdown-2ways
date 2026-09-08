from ._fixtures import make_representative_document


def test_core_ir_semantics_match_phase_b_digest_contract():
    from markitdown.twoways.ir.semantics import (
        native_locator_digest,
        node_semantic_digest,
        node_semantic_text,
    )

    document = make_representative_document()
    node = document.nodes["text1"]

    assert node_semantic_text(node) == "Revenue increased 38%"
    assert node_semantic_digest(node) == (
        "fb93c6dfa659b9c78d79de8c510e5922dd618ab578885412b7f488a53f011f74"
    )
    assert native_locator_digest(node) == (
        "66b331b2ef5a36685407b9f4d8e50c85447625fb9c5c12a1a8d3f0bf5f80f645"
    )


def test_markdown_semantic_aliases_keep_identical_contract():
    from markitdown.twoways.ir.semantics import node_semantic_digest, node_semantic_text
    from markitdown.twoways.markdown.semantics import (
        semantic_text_for_node,
        source_semantic_digest,
    )

    node = make_representative_document().nodes["text1"]
    assert semantic_text_for_node(node) == node_semantic_text(node)
    assert source_semantic_digest(node) == node_semantic_digest(node)
