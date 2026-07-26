# -*- coding: utf-8 -*-
"""A small Markdown subset renderer, plus a LaTeX-to-plain-notation pass.

Written here rather than pulled in as a dependency for the same reason the
archive format avoids them: the build must be reproducible from a checkout with
nothing but a Python interpreter. It handles exactly what the papers and the
specification use — headings, paragraphs, lists, tables, fenced code,
blockquotes, horizontal rules, inline emphasis/code/links, and display or inline
math.

Math is rendered as plain mathematical notation, not typeset. The formulas in
these documents are short statements of identity and coverage, and a readable
`Extract(Pack(F, P)) = F` serves them better than a font-dependent layout engine
would. Where a construct has no honest plain form, the LaTeX source is kept.
"""

from __future__ import annotations

import html
import re

__all__ = ["render_markdown", "split_front_matter", "render_math", "slugify"]


# ---------------------------------------------------------------------------
# front matter
# ---------------------------------------------------------------------------

def split_front_matter(text: str) -> tuple[dict, str]:
    """Return ``(metadata, body)``. Only flat `key: "value"` pairs are read."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    head = text[3:end]
    body = text[end + 4:].lstrip("\n")
    meta: dict[str, str] = {}
    for line in head.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, body


# ---------------------------------------------------------------------------
# math
# ---------------------------------------------------------------------------

_MATH_WORDS = [
    (r"\\operatorname\{([^}]*)\}", r"\1"),
    (r"\\mathrm\{([^}]*)\}", r"\1"),
    (r"\\mathcal\{([^}]*)\}", r"\1"),
    (r"\\text\{([^}]*)\}", r"\1"),
    (r"\\widehat\{([^}]*)\}", r"\1̂"),
    (r"\\hat\{([^}]*)\}", r"\1̂"),
    (r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1) / (\2)"),
]

_MATH_SYMBOLS = {
    r"\Vert": "‖", r"\cdots": "⋯", r"\cdot": "·", r"\ldots": "…",
    r"\bigcup": "⋃", r"\cup": "∪", r"\varnothing": "∅", r"\emptyset": "∅",
    r"\neq": "≠", r"\equiv": "≡", r"\approx": "≈", r"\leq": "≤", r"\geq": "≥",
    r"\forall": "∀", r"\exists": "∃", r"\in": "∈", r"\to": "→",
    r"\Rightarrow": "⇒", r"\rightarrow": "→", r"\Delta": "Δ", r"\delta": "δ",
    r"\Pi": "Π", r"\pi": "π", r"\Sigma": "Σ", r"\sum": "Σ", r"\times": "×",
    r"\quad": "  ", r"\qquad": "    ", r"\,": " ", r"\;": " ", r"\!": "",
    r"\left": "", r"\right": "", r"\begin{cases}": "", r"\end{cases}": "",
    r"\\": "\n", r"\{": "{", r"\}": "}",
}

_SUBSCRIPT = str.maketrans("0123456789+-=()aeioxhklmnpst",
                           "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑᵢₒₓₕₖₗₘₙₚₛₜ")


def _subscripts(source: str) -> str:
    def one(match: re.Match) -> str:
        body = match.group(1) or match.group(2)
        try:
            translated = body.translate(_SUBSCRIPT)
        except Exception:  # pragma: no cover - translate never raises here
            return match.group(0)
        if all(ord(ch) > 127 or ch.isspace() for ch in translated):
            return translated
        return f"_{body}"

    source = re.sub(r"_\{([^{}]*)\}", one, source)
    return re.sub(r"_([A-Za-z0-9])(?![A-Za-z0-9])", lambda m: one(m), source)


def render_math(source: str) -> str:
    """Turn a small LaTeX subset into plain mathematical notation."""
    out = source.strip()
    for pattern, replacement in _MATH_WORDS:
        for _ in range(3):  # nested \operatorname inside \frac, etc.
            new = re.sub(pattern, replacement, out)
            if new == out:
                break
            out = new
    for token, symbol in _MATH_SYMBOLS.items():
        out = out.replace(token, symbol)
    out = _subscripts(out)
    out = re.sub(r"\^\{([^{}]*)\}", r"^(\1)", out)
    # A subscript running straight into the next token reads as one word.
    out = re.sub(r"([₀-ₜ])(?=[A-Za-z(])", r"\1 ", out)
    out = re.sub(r"[ \t]+", " ", out)
    return out.strip()


# ---------------------------------------------------------------------------
# inline
# ---------------------------------------------------------------------------

def _inline(text: str) -> str:
    placeholders: list[str] = []

    def stash(markup: str) -> str:
        placeholders.append(markup)
        return f"\x00{len(placeholders) - 1}\x00"

    # inline code first: nothing inside it is markup
    text = re.sub(r"`([^`]+)`",
                  lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), text)
    # inline math
    text = re.sub(r"(?<!\$)\$([^$\n]+)\$(?!\$)",
                  lambda m: stash(f'<span class="math-inline">'
                                  f'{html.escape(render_math(m.group(1)))}</span>'), text)
    # links
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                  lambda m: stash(f'<a href="{html.escape(m.group(2), quote=True)}">'
                                  f'{html.escape(m.group(1))}</a>'), text)
    # bare URLs
    text = re.sub(r"(?<![\"'=(])\bhttps?://[^\s<>)\]]+",
                  lambda m: stash(f'<a href="{html.escape(m.group(0), quote=True)}" '
                                  f'rel="noreferrer">{html.escape(m.group(0))}</a>'), text)

    text = html.escape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = text.replace("---", "—").replace(" -- ", " — ")

    for index, markup in enumerate(placeholders):
        text = text.replace(f"\x00{index}\x00", markup)
    return text


def slugify(text: str) -> str:
    plain = re.sub(r"[`*_$\\]", "", text).strip().lower()
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", plain).strip("-")
    return slug or "section"


# ---------------------------------------------------------------------------
# block
# ---------------------------------------------------------------------------

def render_markdown(text: str, *, heading_offset: int = 0,
                    collect_headings: list | None = None) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        # fenced code
        if stripped.startswith("```"):
            language = stripped[3:].strip()
            index += 1
            body: list[str] = []
            while index < total and not lines[index].strip().startswith("```"):
                body.append(lines[index])
                index += 1
            index += 1
            klass = f' class="lang-{html.escape(language, quote=True)}"' if language else ""
            out.append(f"<pre{klass}><code>{html.escape(chr(10).join(body))}</code></pre>")
            continue

        # display math
        if stripped == "$$":
            index += 1
            body = []
            while index < total and lines[index].strip() != "$$":
                body.append(lines[index])
                index += 1
            index += 1
            out.append(f'<div class="math-block">'
                       f'{html.escape(render_math(chr(10).join(body)))}</div>')
            continue

        # horizontal rule
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            out.append("<hr>")
            index += 1
            continue

        # heading
        heading = re.match(r"(#{1,6})\s+(.*)", stripped)
        if heading:
            level = min(6, len(heading.group(1)) + heading_offset)
            content = heading.group(2).strip()
            slug = slugify(content)
            if collect_headings is not None and level <= 3:
                collect_headings.append({"level": level, "text": re.sub(r"[`*]", "", content),
                                         "slug": slug})
            out.append(f'<h{level} id="{slug}">{_inline(content)}</h{level}>')
            index += 1
            continue

        # table
        if "|" in stripped and index + 1 < total and re.fullmatch(
                r"\|?[\s:|-]+\|?", lines[index + 1].strip()) and "-" in lines[index + 1]:
            header = _table_row(stripped)
            alignment = _alignments(lines[index + 1].strip())
            index += 2
            rows = []
            while index < total and "|" in lines[index] and lines[index].strip():
                rows.append(_table_row(lines[index].strip()))
                index += 1
            out.append(_table(header, alignment, rows))
            continue

        # blockquote
        if stripped.startswith(">"):
            body = []
            while index < total and lines[index].strip().startswith(">"):
                body.append(lines[index].strip()[1:].strip())
                index += 1
            out.append(f"<blockquote>{_inline(' '.join(body))}</blockquote>")
            continue

        # lists
        if re.match(r"[-*+]\s+", stripped) or re.match(r"\d+[.)]\s+", stripped):
            ordered = bool(re.match(r"\d+[.)]\s+", stripped))
            items: list[str] = []
            while index < total:
                current = lines[index]
                current_stripped = current.strip()
                marker = re.match(r"(?:[-*+]|\d+[.)])\s+(.*)", current_stripped)
                if marker:
                    items.append(marker.group(1))
                    index += 1
                    continue
                if current_stripped and current.startswith(("  ", "\t")) and items:
                    items[-1] += " " + current_stripped
                    index += 1
                    continue
                break
            tag = "ol" if ordered else "ul"
            body = "".join(f"<li>{_inline(item)}</li>" for item in items)
            out.append(f"<{tag}>{body}</{tag}>")
            continue

        # paragraph
        body = [stripped]
        index += 1
        while index < total and lines[index].strip() and not _starts_block(lines[index]):
            body.append(lines[index].strip())
            index += 1
        out.append(f"<p>{_inline(' '.join(body))}</p>")

    return "\n".join(out)


def _starts_block(line: str) -> bool:
    stripped = line.strip()
    return bool(
        stripped.startswith(("```", ">", "$$", "#"))
        or re.match(r"[-*+]\s+", stripped)
        or re.match(r"\d+[.)]\s+", stripped)
        or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped)
        or ("|" in stripped and stripped.startswith("|"))
    )


def _table_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [cell.strip() for cell in cells]


def _alignments(line: str) -> list[str]:
    out = []
    for cell in line.strip().strip("|").split("|"):
        cell = cell.strip()
        if cell.startswith(":") and cell.endswith(":"):
            out.append("center")
        elif cell.endswith(":"):
            out.append("right")
        else:
            out.append("left")
    return out


def _table(header: list[str], alignment: list[str], rows: list[list[str]]) -> str:
    def cell(tag: str, value: str, position: int) -> str:
        align = alignment[position] if position < len(alignment) else "left"
        style = f' style="text-align:{align}"' if align != "left" else ""
        return f"<{tag}{style}>{_inline(value)}</{tag}>"

    head = "".join(cell("th", value, i) for i, value in enumerate(header))
    body = "".join(
        "<tr>" + "".join(cell("td", value, i) for i, value in enumerate(row)) + "</tr>"
        for row in rows
    )
    return (f'<div class="table-scroll"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{body}</tbody></table></div>")
