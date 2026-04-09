"""Format a single assembled article with metadata categories and templates."""

import re


def _extract_band_number(band: str) -> str:
    """Extract the leading integer from a band string like 'Band 14' → '14'."""
    m = re.search(r"\d+", band)
    return m.group(0) if m else band


def build_artikel_template(
    bauwerk: str,
    literaturangabe: str,
    ort: str,
    autoren: list[str],
    eigenschaft: str,
    band: str,
    *,
    seite_von: int | None = None,
    seite_bis: int | None = None,
    chunk: int | None = None,
    chunkseite: int | None = None,
    davor: str | None = None,
    danach: str | None = None,
) -> str:
    """Build the {{Artikel}} metadata template string (without article body)."""
    band_num = _extract_band_number(band)

    template_lines = [
        "{{Artikel",
        f"|Band={band_num}",
        f"|Chunk={chunk if chunk is not None else ''}",
        f"|Chunkseite={chunkseite if chunkseite is not None else ''}",
        f"|Originalseitenvon={seite_von if seite_von is not None else ''}",
        f"|Originalseitenbis={seite_bis if seite_bis is not None else ''}",
        f"|Lemma={bauwerk}",
        f"|Typ={eigenschaft}",
        f"|Ort={ort}",
        f"|davor={davor or ''}",
        f"|danach={danach or ''}",
    ]
    for i, autor in enumerate(autoren, 1):
        template_lines.append(f"|AutorIn{i}={autor}")
    template_lines.append("}}")

    return "\n".join(template_lines)


def format_article(
    bauwerk: str,
    content: str,
    literaturangabe: str,
    ort: str,
    autoren: list[str],
    eigenschaft: str,
    band: str,
    *,
    seite_von: int | None = None,
    seite_bis: int | None = None,
    chunk: int | None = None,
    chunkseite: int | None = None,
    davor: str | None = None,
    danach: str | None = None,
) -> str:
    """Format the final article with an {{Artikel}} metadata template."""
    template = build_artikel_template(
        bauwerk,
        literaturangabe,
        ort,
        autoren,
        eigenschaft,
        band,
        seite_von=seite_von,
        seite_bis=seite_bis,
        chunk=chunk,
        chunkseite=chunkseite,
        davor=davor,
        danach=danach,
    )
    return template + "\n\n" + content + "\n"
