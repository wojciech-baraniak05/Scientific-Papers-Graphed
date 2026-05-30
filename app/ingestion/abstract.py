from __future__ import annotations


def decode_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None

    positioned: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if not positions:
            continue
        for pos in positions:
            positioned.append((pos, word))

    if not positioned:
        return None

    positioned.sort(key=lambda pair: pair[0])
    return " ".join(word for _, word in positioned)
