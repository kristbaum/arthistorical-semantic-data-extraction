"""Format a single assembled article with metadata categories and templates."""


def format_article(
    bauwerk: str,
    content: str,
    literaturangabe: str,
    ort: str,
    autoren: list[str],
    eigenschaft: str,
    band: str,
) -> str:
    """Format the final article with metadata categories and templates."""
    parts: list[str] = []

    # Categories
    categories: list[str] = []
    if ort:
        categories.append(f"[[Kategorie:{ort}]]")
    for autor in autoren:
        autor = autor.strip()
        if autor:
            categories.append(f"[[Kategorie:{autor}]]")
    if eigenschaft:
        categories.append(f"[[Kategorie:{eigenschaft}]]")
    if band:
        categories.append(f"[[Kategorie:{band}]]")

    # Literaturangabe template
    if literaturangabe:
        parts.append(f"{{{{Literaturangabe|text={literaturangabe}}}}}")
        parts.append("")

    # Main content
    parts.append(content)

    # Categories at the bottom
    if categories:
        parts.append("")
        parts.extend(categories)

    return "\n".join(parts) + "\n"
