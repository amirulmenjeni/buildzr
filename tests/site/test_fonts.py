"""Inter metrics and the tier-aware label wrap."""

from __future__ import annotations

from buildzr.site import fonts


def test_measure_known_widths() -> None:
    # Inter regular 'i' is 496/2048 em, 'W' bold is wider than 'W' regular.
    assert abs(fonts.measure("i", 16) - 16 * 496 / 2048) < 1e-9
    assert fonts.measure("W", 16, "bold") > fonts.measure("W", 16)
    assert fonts.measure("", 16) == 0


def test_wrap_keeps_tier_weight_size_on_every_piece() -> None:
    lines = [
        {"text": "A rather long service name that cannot fit", "tier": 0, "weight": "bold"},
        {"text": "[Container: Go]", "tier": 1, "size": 12},
        {"text": "Words " * 30, "tier": 2, "size": 12, "italic": True},
    ]
    out = fonts.wrap(lines, 150, 16)
    assert len(out) > 3
    for piece in out:
        src = next(ln for ln in lines if piece["text"].split()[0] in str(ln["text"]))
        assert piece["tier"] == src["tier"]
        assert piece.get("weight") == src.get("weight")
        assert piece.get("size") == src.get("size")
        assert piece.get("italic") == src.get("italic")
        w = fonts.measure(piece["text"], piece.get("size", 16), piece.get("weight", "normal"))
        assert w <= 150 or " " not in piece["text"]
    # a short line stays one line, in order
    assert [p["text"] for p in out if p["tier"] == 1] == ["[Container: Go]"]
    assert [p["tier"] for p in out] == sorted(p["tier"] for p in out)


def test_wrap_does_not_split_a_long_word_and_drops_empty_text() -> None:
    out = fonts.wrap([{"text": "Supercalifragilisticexpialidocious", "tier": 0}, {"text": "  ", "tier": 1}], 40)
    assert [p["text"] for p in out] == ["Supercalifragilisticexpialidocious"]


def test_leaf_size_matches_spike_rule() -> None:
    lines = [{"text": "Billing API", "tier": 0, "weight": "bold"},
             {"text": "[Container: Go]", "tier": 1, "size": 12},
             {"text": "Invoicing and payment API.", "tier": 2, "size": 12}]
    w, h, wrapped = fonts.leaf_size(lines, 16)
    assert w == 240
    expected = 2 * 16 + 16 * 1.25 + 12 * 1.25 * 2
    assert h == max(120, int(expected + 0.999))
    assert [p["text"] for p in wrapped] == [ln["text"] for ln in lines]
    # many lines make the box taller than the minimum
    _, h2, _ = fonts.leaf_size([{"text": "word " * 80, "tier": 2, "size": 12}], 16)
    assert h2 > 120
