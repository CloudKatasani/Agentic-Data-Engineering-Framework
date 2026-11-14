"""Output formats for stage documents: Markdown (as written), HTML and Word (.docx).

Agents write Markdown. When a stage is set to another format, each Markdown document it produced
is also rendered to that format and handed over with it, so reviewers and downstream teams get the
file type they work in. Rendering is deterministic (same input, same bytes), which keeps approvals
tied to exact file hashes. No external library is needed.
"""
from __future__ import annotations

import html
import io
import re
import zipfile

FORMATS: dict[str, dict] = {
    "markdown": {"label": "Markdown", "ext": "md", "media": "text/markdown"},
    "html": {"label": "HTML (opens in any browser, prints to PDF)", "ext": "html", "media": "text/html"},
    "docx": {"label": "Word (.docx)", "ext": "docx",
             "media": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
}
BINARY_EXT = (".docx", ".zip", ".db", ".png", ".jpg", ".pdf", ".parquet")


# ----------------------------------------------------------------------------- parse
def parse(md: str) -> list[tuple]:
    """Markdown to blocks: ("h", level, text) ("p", text) ("ul"|"ol", [items]) ("code", text) ("table", head, rows) ("quote", text)."""
    out: list[tuple] = []
    lines = (md or "").replace("\r\n", "\n").split("\n")
    i = 0
    cells = lambda ln: [c.strip() for c in ln.strip().strip("|").split("|")]  # noqa: E731
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append(("code", "\n".join(lines[i + 1:j])))
            i = j + 1
        elif m := re.match(r"^(#{1,6})\s+(.*)$", ln):
            out.append(("h", len(m.group(1)), m.group(2).strip()))
            i += 1
        elif ln.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]):
            head, rows, i = cells(ln), [], i + 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(cells(lines[i]))
                i += 1
            out.append(("table", head, rows))
        elif re.match(r"^\s*([-*+]|\d+[.)])\s+", ln):
            kind = "ol" if re.match(r"^\s*\d+[.)]\s+", ln) else "ul"
            items = []
            while i < len(lines) and (re.match(r"^\s*([-*+]|\d+[.)])\s+", lines[i]) or (lines[i].startswith("  ") and lines[i].strip() and items)):
                if re.match(r"^\s*([-*+]|\d+[.)])\s+", lines[i]):
                    items.append(re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", lines[i]))
                else:
                    items[-1] += " " + lines[i].strip()
                i += 1
            out.append((kind, items))
        elif ln.startswith(">"):
            j = i
            while j < len(lines) and lines[j].startswith(">"):
                j += 1
            out.append(("quote", " ".join(x.lstrip("> ").strip() for x in lines[i:j])))
            i = j
        elif not ln.strip() or re.match(r"^\s*(-{3,}|\*{3,})\s*$", ln) or ln.strip().startswith("<!--"):
            i += 1
        else:
            j = i
            while j < len(lines) and lines[j].strip() and not re.match(r"^(#{1,6}\s|```|>|\s*([-*+]|\d+[.)])\s+|\s*\|)", lines[j]):
                j += 1
            out.append(("p", " ".join(x.strip() for x in lines[i:max(j, i + 1)])))
            i = max(j, i + 1)
    return out


_INLINE = re.compile(r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|(?<![\w*])\*[^*\s][^*]*\*(?![\w*]))")


def runs(text: str) -> list[tuple[str, str]]:
    """Inline text as (style, text) runs; style is "", "b", "i" or "code"."""
    out = []
    for part in _INLINE.split(text or ""):
        if not part:
            continue
        if part.startswith("**"):
            out.append(("b", part[2:-2]))
        elif part.startswith("`"):
            out.append(("code", part[1:-1]))
        elif part.startswith("["):
            out.append(("", re.sub(r"^\[([^\]]+)\]\([^)]+\)$", r"\1", part)))
        elif part.startswith("*"):
            out.append(("i", part[1:-1]))
        else:
            out.append(("", part))
    return out


# ----------------------------------------------------------------------------- HTML
def _h(text: str) -> str:
    tag = {"b": "strong", "i": "em", "code": "code"}
    return "".join(f"<{tag[s]}>{html.escape(t)}</{tag[s]}>" if s else html.escape(t) for s, t in runs(text))


def to_html(md: str, title: str) -> str:
    body = []
    for b in parse(md):
        if b[0] == "h":
            body.append(f"<h{min(b[1], 4)}>{_h(b[2])}</h{min(b[1], 4)}>")
        elif b[0] == "p":
            body.append(f"<p>{_h(b[1])}</p>")
        elif b[0] in ("ul", "ol"):
            body.append(f"<{b[0]}>" + "".join(f"<li>{_h(x)}</li>" for x in b[1]) + f"</{b[0]}>")
        elif b[0] == "code":
            body.append(f"<pre>{html.escape(b[1])}</pre>")
        elif b[0] == "quote":
            body.append(f"<blockquote>{_h(b[1])}</blockquote>")
        elif b[0] == "table":
            body.append("<table><thead><tr>" + "".join(f"<th>{_h(c)}</th>" for c in b[1]) + "</tr></thead><tbody>"
                        + "".join("<tr>" + "".join(f"<td>{_h(c)}</td>" for c in r) + "</tr>" for r in b[2]) + "</tbody></table>")
    css = ("body{font:15px/1.5 Calibri,Segoe UI,Arial,sans-serif;max-width:960px;margin:32px auto;padding:0 20px;color:#1b2333}"
           "h1,h2,h3,h4{line-height:1.25;margin:1.4em 0 .5em}table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}"
           "th,td{border:1px solid #c9d1e0;padding:6px 9px;text-align:left;vertical-align:top}th{background:#eef2f9}"
           "pre{background:#f3f5f9;padding:12px;border-radius:6px;overflow:auto;font-size:13px}code{background:#f3f5f9;padding:1px 4px;border-radius:3px}"
           "blockquote{border-left:4px solid #c9d1e0;margin:12px 0;padding:4px 14px;color:#4a5670}"
           "@media print{body{margin:0;max-width:none}}")
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{css}</style></head><body>\n" + "\n".join(body) + "\n</body></html>\n")


# ----------------------------------------------------------------------------- Word
def _x(text: str) -> str:
    return html.escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text), quote=False)


def _r(text: str, style: str = "", size: int | None = None) -> str:
    props = ("<w:b/>" if style == "b" else "") + ("<w:i/>" if style == "i" else "") \
        + ('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>' if style == "code" else "") + (f'<w:sz w:val="{size}"/>' if size else "")
    return f'<w:r>{f"<w:rPr>{props}</w:rPr>" if props else ""}<w:t xml:space="preserve">{_x(text)}</w:t></w:r>'


def _p(text: str, style: str | None = None, prefix: str = "", indent: int = 0, bold: bool = False) -> str:
    ppr = (f'<w:pStyle w:val="{style}"/>' if style else "") + (f'<w:ind w:left="{indent}"/>' if indent else "")
    body = (_r(prefix) if prefix else "") + "".join(_r(t, "b" if bold and not s else s) for s, t in runs(text))
    return f'<w:p>{f"<w:pPr>{ppr}</w:pPr>" if ppr else ""}{body}</w:p>'


def to_docx(md: str, title: str) -> bytes:
    body = []
    for b in parse(md):
        if b[0] == "h":
            body.append(_p(b[2], f"Heading{min(b[1], 3)}"))
        elif b[0] == "p":
            body.append(_p(b[1]))
        elif b[0] in ("ul", "ol"):
            body += [_p(x, prefix=("• " if b[0] == "ul" else f"{n}. "), indent=360) for n, x in enumerate(b[1], start=1)]
        elif b[0] == "quote":
            body.append(_p(b[1], indent=480))
        elif b[0] == "code":
            body += [f'<w:p><w:pPr><w:spacing w:after="0"/></w:pPr>{_r(line or " ", "code", 18)}</w:p>' for line in b[1].split("\n")]
        elif b[0] == "table":
            width = max(len(b[1]), *(len(r) for r in b[2])) if b[2] else len(b[1])
            border = "".join(f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="AAB4C8"/>'
                             for e in ("top", "left", "bottom", "right", "insideH", "insideV"))
            rows = []
            for n, r in enumerate([b[1]] + b[2]):
                tcs = "".join("<w:tc><w:tcPr>" + ('<w:shd w:val="clear" w:color="auto" w:fill="EEF2F9"/>' if n == 0 else "")
                              + f"</w:tcPr>{_p(c, bold=n == 0)}</w:tc>" for c in (r + [""] * width)[:width])
                rows.append(f"<w:tr>{tcs}</w:tr>")
            body.append(f'<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>{border}</w:tblBorders></w:tblPr>'
                        + "".join(rows) + "</w:tbl><w:p/>")
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {ns}><w:body>' + "".join(body)
                + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
                "</w:body></w:document>")

    def heading(n: int, size: int) -> str:
        return (f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/><w:basedOn w:val="Normal"/>'
                f'<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="100"/><w:outlineLvl w:val="{n - 1}"/></w:pPr>'
                f'<w:rPr><w:b/><w:sz w:val="{size}"/></w:rPr></w:style>')
    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {ns}><w:docDefaults><w:rPrDefault><w:rPr>'
              '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr></w:rPrDefault>'
              '<w:pPrDefault><w:pPr><w:spacing w:after="120"/></w:pPr></w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
              + heading(1, 34) + heading(2, 28) + heading(3, 24) + "</w:styles>")
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>',
        "word/_rels/document.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "docProps/core.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        f'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{_x(title)}</dc:title><dc:creator>DataCrew AI</dc:creator></cp:coreProperties>',
        "word/styles.xml": styles, "word/document.xml": document,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items():      # fixed timestamps: the same document always gives the same bytes
            z.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), content)
    return buf.getvalue()


def render(md: str, fmt: str, title: str) -> str | bytes:
    if fmt == "html":
        return to_html(md, title)
    if fmt == "docx":
        return to_docx(md, title)
    if fmt == "markdown":
        return md
    raise ValueError(f"Unknown output format `{fmt}`; choose one of {', '.join(FORMATS)}")
