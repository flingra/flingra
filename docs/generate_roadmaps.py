from html.parser import HTMLParser
from pathlib import Path
import re
import textwrap


ROOT = Path(__file__).resolve().parent
PAGE_W, PAGE_H = 595, 842
LEFT, RIGHT = 48, 48
TOP, BOTTOM = 770, 54


class RoadmapParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.current = None
        self.row = None
        self.cell = None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("head", "style", "script"):
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "div" and "eyebrow" in attrs.get("class", ""):
            self._start_block("eyebrow")
        elif tag in ("h1", "h2", "h3", "p", "li"):
            self._start_block(tag)
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("head", "style", "script"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ("h1", "h2", "h3", "p", "li", "div") and self.current:
            self._finish_block()
        elif tag in ("td", "th") and self.row is not None and self.cell is not None:
            cell = self._clean("".join(self.cell))
            if cell:
                self.row.append(cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.blocks.append(("row", "  |  ".join(self.row)))
            self.row = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(data)
        elif self.current is not None:
            self.current[1].append(data)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def _start_block(self, kind):
        if self.current:
            self._finish_block()
        self.current = [kind, []]

    def _finish_block(self):
        kind, fragments = self.current
        text = self._clean("".join(fragments))
        if text:
            self.blocks.append((kind, text))
        self.current = None

    @staticmethod
    def _clean(value):
        return re.sub(r"\s+", " ", value).strip()


def ascii_text(value):
    value = value.replace("\u00b7", "-").replace("\u2014", "-").replace("\u2013", "-")
    value = value.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return value.encode("ascii", "ignore").decode("ascii")


def pdf_escape(value):
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_operator(text, x, y, size, font="F1", color=(0.12, 0.16, 0.25)):
    r, g, b = color
    return (
        f"{r:.3f} {g:.3f} {b:.3f} rg BT /{font} {size} Tf "
        f"1 0 0 1 {x} {y} Tm ({pdf_escape(text)}) Tj ET\n"
    )


def render_blocks(blocks):
    pages = []
    current = []
    y = TOP

    def new_page():
        nonlocal current, y
        if current:
            pages.append(current)
        current = []
        y = TOP

    for kind, raw_text in blocks:
        text = ascii_text(raw_text)
        if not text:
            continue
        if kind == "h1":
            size, font, width, gap = 23, "F2", 53, 12
        elif kind == "h2":
            size, font, width, gap = 15, "F2", 68, 9
        elif kind == "h3":
            size, font, width, gap = 11.5, "F2", 91, 4
        elif kind == "eyebrow":
            size, font, width, gap = 9, "F2", 110, 5
        elif kind == "li":
            size, font, width, gap = 9.3, "F1", 94, 2
            text = "- " + text
        elif kind == "row":
            size, font, width, gap = 8.2, "F1", 105, 5
        else:
            size, font, width, gap = 9.5, "F1", 96, 5

        lines = textwrap.wrap(text, width=width, break_long_words=True, break_on_hyphens=False) or [""]
        line_height = size * 1.35
        needed = len(lines) * line_height + gap
        if y - needed < BOTTOM:
            new_page()
        for line in lines:
            if kind in ("h1", "h2", "h3", "eyebrow"):
                color = (0.03, 0.48, 0.44) if kind != "h1" else (0.08, 0.14, 0.25)
            else:
                color = (0.22, 0.27, 0.35)
            current.append(text_operator(line, LEFT, y, size, font, color))
            y -= line_height
        y -= gap

    if current:
        pages.append(current)
    return pages


def page_stream(lines, index, total, title):
    parts = [
        "0.03 0.48 0.44 rg 0 798 595 44 re f\n",
        text_operator("FLINGRA  /  BUILD ROADMAP", LEFT, 815, 10, "F2", (1, 1, 1)),
        text_operator(title, LEFT, 783, 8, "F1", (1, 1, 1)),
        "0.82 0.85 0.89 RG 48 43 m 547 43 l S\n",
        text_operator(f"Flingra planning document  |  Page {index} of {total}", LEFT, 28, 8, "F1", (0.34, 0.39, 0.47)),
    ]
    parts.extend(lines)
    return "".join(parts).encode("ascii")


def write_pdf(path, title, pages):
    objects = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")
    next_obj = 3
    font_regular = next_obj
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_bold = font_regular + 1
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    next_obj = font_bold + 1
    page_refs = [next_obj + 2 * index for index in range(len(pages))]
    kids = " ".join(f"{page_ref} 0 R" for page_ref in page_refs)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()

    for index, content_lines in enumerate(pages, start=1):
        page_obj = page_refs[index - 1]
        content_obj = page_obj + 1
        stream = page_stream(content_lines, index, len(pages), title)
        objects.extend([
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> "
                f"/Contents {content_obj} 0 R >>"
            ).encode(),
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream",
        ])

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    path.write_bytes(output)
    validate_pdf(path, len(pages))


def validate_pdf(path, expected_pages):
    data = path.read_bytes()
    if not data.startswith(b"%PDF-1.4\n") or not data.rstrip().endswith(b"%%EOF"):
        raise ValueError(f"{path.name} is missing a valid PDF header or EOF marker")
    if data.count(b"/Type /Page /") != expected_pages:
        raise ValueError(f"{path.name} has an unexpected number of page objects")
    xref_offset = int(data.rsplit(b"startxref\n", 1)[1].splitlines()[0])
    if not data[xref_offset:xref_offset + 5] == b"xref\n":
        raise ValueError(f"{path.name} has an invalid cross-reference offset")
    print(f"Verified {path.name}: {expected_pages} page(s), {len(data)} bytes")


def build(source_name, output_name, title):
    parser = RoadmapParser()
    parser.feed((ROOT / source_name).read_text(encoding="utf-8"))
    pages = render_blocks(parser.blocks)
    write_pdf(ROOT / output_name, title, pages)
    print(f"Wrote {output_name}: {len(pages)} page(s)")


if __name__ == "__main__":
    build("frontend-roadmap.html", "frontend-roadmap.pdf", "Frontend roadmap")
    build("backend-roadmap.html", "backend-roadmap.pdf", "Backend roadmap")
