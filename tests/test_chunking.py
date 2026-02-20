from book2audiobook.core.chunking import backend_chunk_target, chunk_text


def test_sentence_aware_chunking_and_max_limit() -> None:
    text = " ".join(["Sentence one.", "Sentence two!", "Sentence three?", "Sentence four."] * 60)
    chunks = chunk_text(text, target_chars=220, hard_max_chars=300)
    assert len(chunks) > 1
    assert all(len(chunk) <= 300 for chunk in chunks)


def test_hard_split_for_long_sentence() -> None:
    text = "A" * 1200
    chunks = chunk_text(text, target_chars=200, hard_max_chars=250)
    assert len(chunks) >= 4
    assert all(len(chunk) <= 250 for chunk in chunks)


def test_deterministic_chunking_output() -> None:
    text = "This is deterministic. " * 200
    first = chunk_text(text, target_chars=260, hard_max_chars=300)
    second = chunk_text(text, target_chars=260, hard_max_chars=300)
    assert first == second


def test_backend_chunk_target_scales_with_hard_max() -> None:
    assert backend_chunk_target(2200) == 1980


def test_backend_chunk_target_respects_floor_and_ceiling() -> None:
    assert backend_chunk_target(1300) == 1300
    assert backend_chunk_target(4000) == 3600
