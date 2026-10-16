#!/usr/bin/env python3
"""Tách BRD/SRS (HTML) thành các tệp Markdown nhỏ trong docs/split_spec/.

BẢN DỰNG LẠI (reconstruction): tệp gốc scripts/split_spec.py đã mất; bản này được viết lại
từ đầu ra hiện có của docs/split_spec/ nên có thể lệch vài chi tiết định dạng so với bản gốc.
Chạy: python scripts/split_spec.py [--check]   (--check: so với thư mục hiện có, không ghi)
"""
import html, os, re, sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
OUT = os.path.join(DOCS, "split_spec")

SOURCES = [("BRD", "brd-v5_3.html"), ("SRS", "srs-v5_3.html")]
# h1 bị tách tiếp theo mức nào: 4 theo h3 (BR-xx / UC-xx), 10/12/15 (SRS) theo h2
SPLIT_H3 = {"BRD": {"4"}, "SRS": {"4"}}
SPLIT_H2 = {"BRD": set(), "SRS": {"10", "12", "15"}}

NAMES = {
    "BRD|mục 1": "brd-01-tong-quan.md",
    "BRD|mục 2": "brd-02-pham-vi.md",
    "BRD|mục 3": "brd-03-chu-the.md",
    "BRD|BR-01 (mục 4)": "brd-04-br-01.md",
    "BRD|BR-02 (mục 4)": "brd-04-br-02.md",
    "BRD|BR-03 (mục 4)": "brd-04-br-03.md",
    "BRD|BR-04 (mục 4)": "brd-04-br-04.md",
    "BRD|BR-05 (mục 4)": "brd-04-br-05.md",
    "BRD|BR-06 (mục 4)": "brd-04-br-06.md",
    "BRD|BR-07 (mục 4)": "brd-04-br-07.md",
    "BRD|BR-08 (mục 4)": "brd-04-br-08.md",
    "BRD|BR-09 (mục 4)": "brd-04-br-09.md",
    "BRD|BR-10 (mục 4)": "brd-04-br-10.md",
    "BRD|BR-11 (mục 4)": "brd-04-br-11.md",
    "BRD|mục 5": "brd-05-vong-doi-don.md",
    "BRD|mục 6": "brd-06-tin-cay-de-doa.md",
    "BRD|mục 7": "brd-07-phap-ly.md",
    "BRD|mục 8": "brd-08-nghiem-thu.md",
    "BRD|mục 9": "brd-09-rui-ro.md",
    "BRD|mục 10": "brd-10-lo-trinh.md",
    "BRD|mục 11": "brd-11-thuat-ngu.md",
    "SRS|mục 0": "srs-00-lich-su.md",
    "SRS|mục 1": "srs-01-pham-vi-thuat-ngu.md",
    "SRS|mục 2": "srs-02-kien-truc.md",
    "SRS|mục 3": "srs-03-phan-quyen.md",
    "SRS|UC-00 (mục 4)": "srs-04-uc-00.md",
    "SRS|UC-01 (mục 4)": "srs-04-uc-01.md",
    "SRS|UC-02 (mục 4)": "srs-04-uc-02.md",
    "SRS|UC-03 (mục 4)": "srs-04-uc-03.md",
    "SRS|UC-04 (mục 4)": "srs-04-uc-04.md",
    "SRS|UC-05 (mục 4)": "srs-04-uc-05.md",
    "SRS|UC-06 (mục 4)": "srs-04-uc-06.md",
    "SRS|UC-07 (mục 4)": "srs-04-uc-07.md",
    "SRS|UC-08 (mục 4)": "srs-04-uc-08.md",
    "SRS|UC-09 (mục 4)": "srs-04-uc-09.md",
    "SRS|mục 5": "srs-05-may-trang-thai.md",
    "SRS|mục 6": "srs-06-eip712.md",
    "SRS|mục 7": "srs-07-rest-api.md",
    "SRS|mục 8": "srs-08-giao-dien.md",
    "SRS|mục 9": "srs-09-database.md",
    "SRS|mục 10 (phần dẫn)": "srs-10-contract.md",
    "SRS|mục 10.1": "srs-101-quyet-dinh-thiet-ke.md",
    "SRS|mục 10.2": "srs-102-foundry.md",
    "SRS|mục 11": "srs-11-lo-trinh.md",
    "SRS|mục 12.1": "srs-121-test-contract.md",
    "SRS|mục 12.2": "srs-122-test-tich-hop-e2e.md",
    "SRS|mục 12.3": "srs-123-test-hien-co-ci.md",
    "SRS|mục 13": "srs-13-phi-chuc-nang.md",
    "SRS|mục 14": "srs-14-truy-vet.md",
    "SRS|mục 15 (phần dẫn)": "srs-15-nen-tang.md",
    "SRS|mục 15.1": "srs-151-hien-trang.md",
    "SRS|mục 15.2": "srs-152-loi-bao-mat.md",
    "SRS|mục 15.3": "srs-153-giai-doan-0.md"
}

HEADER = ("<!-- Nguồn: {doc}-SLOPEE-MVP-01 v5.3, {ref}. Sinh bởi scripts/split_spec.py từ {src}. "
          "ĐÃ ĐÓNG BĂNG: không sửa tay, sửa nguồn rồi chạy lại. -->")


# ---------------------------------------------------------------- HTML -> Markdown
class MD(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []        # danh sách khối Markdown
        self.stack = []         # ngăn xếp thẻ
        self.buf = []           # văn bản dòng hiện tại
        self.lists = []         # ngăn xếp danh sách: [kind, counter]
        self.items = []         # các mục danh sách đang mở: danh sách dòng
        self.table = None
        self.row = None
        self.cell = None
        self.pre = None
        self.cls = []
        self.skip = 0

    # tiện ích
    def _flush_para(self):
        t = "".join(self.buf)
        self.buf = []
        return t

    def _emit(self, text):
        text = text.strip("\n")
        if text.strip():
            self.blocks.append(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.cls.append(a.get("class", ""))
        self.stack.append(tag)
        c = a.get("class", "")
        if tag in ("style", "script"):
            self.skip += 1
        if self.pre is not None:
            if tag == "code":
                return
        if tag in ("strong", "b"):
            self.buf.append("**")
        elif tag in ("em", "i"):
            self.buf.append("*")
        elif tag == "code" and self.pre is None:
            self.buf.append("`")
        elif tag == "br":
            self.buf.append("  \n")
        elif tag == "pre":
            self.pre = []
        elif tag in ("ul", "ol"):
            if self.lists or self.buf and "".join(self.buf).strip():
                self._close_item_text()
            self.lists.append([tag, 0])
        elif tag == "li":
            self.lists[-1][1] += 1
            self.items.append({"kind": self.lists[-1][0], "n": self.lists[-1][1],
                               "depth": len(self.lists) - 1, "lines": [], "pos": len(self._pending)})
            self.buf = []
        elif tag == "table":
            self.table = []
        elif tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = {"head": tag == "th", "span": int(a.get("colspan", 1))}
            self.buf = []
        elif tag == "span" and "badge" in c:
            self.buf.append('<span class="%s">' % c)
        elif tag == "div" and ("note-box" in c or "formula-box" in c):
            self.buf = []

    def _close_item_text(self):
        t = self._flush_para().strip()
        if self.items and t:
            self.items[-1]["lines"].append(t)

    def handle_endtag(self, tag):
        c = self.cls.pop() if self.cls else ""
        if self.stack:
            self.stack.pop()
        if tag in ("style", "script"):
            self.skip -= 1
            return
        if self.pre is not None and tag == "code":
            return
        if tag in ("strong", "b"):
            self.buf.append("**")
        elif tag in ("em", "i"):
            self.buf.append("*")
        elif tag == "code" and self.pre is None:
            self.buf.append("`")
        elif tag == "pre":
            code = "".join(self.pre).strip("\n")
            self.pre = None
            self._emit("```%s\n%s\n```" % (guess_lang(code), code))
        elif tag == "p":
            t = self._flush_para().strip()
            if self.items and self.lists:
                if t:
                    self.items[-1]["lines"].append(t)
            else:
                self._emit(t)
        elif tag == "li":
            self._close_item_text()
            it = self.items.pop()
            self._add_item(it)
        elif tag in ("ul", "ol"):
            self.lists.pop()
            if not self.lists:
                self._emit("\n".join(self._pending))
                self._pending = []
        elif tag in ("td", "th"):
            t = " ".join(self._flush_para().split())
            self.cell["text"] = t
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr":
            self.table.append(self.row)
            self.row = None
        elif tag == "table":
            self._emit(render_table(self.table))
            self.table = None
        elif tag == "div":
            t = self._flush_para()
            t = "\n".join(l.lstrip() for l in t.split("\n")).strip()
            if t:
                self._emit(t)
        elif tag in ("h1", "h2", "h3", "h4"):
            t = " ".join(self._flush_para().split())
            self.blocks.append(("H", int(tag[1]), t))
        elif tag == "span" and "badge" in c:
            self.buf.append("</span>")

    _pending = []

    def _add_item(self, it):
        ind = "  " * it["depth"]
        marker = "-" if it["kind"] == "ul" else "%d." % it["n"]
        pad = " " if it["kind"] == "ul" else "  "
        lines = it["lines"] or [""]
        out = [ind + marker + pad + lines[0].replace("\n", "\n" + ind + "  ")]
        for extra in lines[1:]:
            out.append(ind + "  " + extra)
        # mục con (đã được thêm trước) nằm sau; ghi theo thứ tự đóng nên chèn mục cha lên trước các con
        # của chính nó: tìm vị trí đầu của nhóm con
        self._pending.insert(it["pos"], "\n".join(out))

    _pending_depth = []

    def handle_data(self, data):
        if self.skip:
            return
        if self.pre is not None:
            self.pre.append(data)
            return
        if not self.stack or self.stack[-1] in ("body", "html", "ul", "ol", "table", "tr", "div") and not data.strip():
            if not (self.stack and self.stack[-1] == "div"):
                return
        if "\n" in data:
            data = re.sub(r"\s+", " ", data)
        if self.stack and self.stack[-1] != "code":
            data = data.replace("$", "\\$").replace("[", "\\[").replace("]", "\\]")
        if self.buf and self.buf[-1].endswith("\n"):
            data = data.lstrip()
        self.buf.append(data)


def guess_lang(code):
    if re.search(r"^(CREATE TABLE|INSERT|ALTER|SELECT|--)", code, re.M):
        return "sql"
    if re.search(r"pragma solidity|contract \w+|^import ", code, re.M):
        return "solidity"
    if re.search(r"^(forge|cast|anvil|\./|pytest|pip|npm|cd |git )", code, re.M):
        return "bash"
    return "text"


def esc_cell(t):
    if t == "-":
        return "\\-"
    if t == "#":
        return "\\#"
    return t.replace("|", "\\|")


def render_table(rows):
    if not rows:
        return ""
    width = max(sum(c["span"] for c in r) for r in rows)
    lines = []
    if not any(c["head"] for c in rows[0]):
        rows = [[{"head": True, "span": 1, "text": ""} for _ in range(width)]] + rows
    for i, r in enumerate(rows):
        cells = []
        for c in r:
            cells.append(esc_cell(c["text"]))
            cells.extend([""] * (c["span"] - 1))
        cells += [""] * (width - len(cells))
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("|" + "|".join(["---"] * width) + "|")
    return "\n".join(lines)


def html_to_blocks(fragment):
    p = MD()
    p._pending, p._pending_depth = [], []
    p.feed(fragment)
    p.close()
    return p.blocks


# ---------------------------------------------------------------- tách tài liệu
def split_body(doc, src):
    h = open(os.path.join(DOCS, src), encoding="utf-8").read()
    return h[h.index("<body"):]


def slug_ref(doc, kind, num, title):
    """Trả về (tên tệp, chuỗi nguồn) theo bảng NAMES."""
    return None


def main(check=False):
    os.makedirs(OUT, exist_ok=True)
    written = {}
    for doc, src in SOURCES:
        body = split_body(doc, src)
        blocks = html_to_blocks(body)
        sections = []          # (ref, title, level, [blocks])
        cur = {"ref": None, "title": None, "lvl": 0, "blocks": [], "id": None}
        preface = cur["blocks"]
        h1id = None
        for b in blocks:
            if isinstance(b, tuple):
                _, lvl, text = b
                text = html.unescape(text)
                plain = text.replace("`", "")
                m1 = re.match(r"^(\d+)\.\s", plain)
                m2 = re.match(r"^(\d+\.\d+)\.\s", text)
                m3 = re.match(r"^((?:BR|UC)-\d+):", text)
                if lvl == 1 and m1:
                    h1id = m1.group(1)
                    cur = {"ref": "mục " + h1id, "title": plain, "lvl": 1, "raw": text, "blocks": [], "id": h1id}
                    sections.append(cur)
                    continue
                if lvl == 3 and m3 and h1id in SPLIT_H3[doc]:
                    cur = {"ref": "%s (mục %s)" % (m3.group(1), h1id), "title": plain, "lvl": 3,
                           "blocks": [], "id": m3.group(1)}
                    sections.append(cur)
                    continue
                if lvl == 2 and m2 and h1id in SPLIT_H2[doc] and m2.group(1).startswith(h1id + "."):
                    # phần dẫn của mục cha: gắn nhãn
                    for s in reversed(sections):
                        if s["lvl"] == 1 and s["id"] == h1id and not s.get("lead"):
                            s["lead"] = True
                            s["ref"] = "mục %s (phần dẫn)" % h1id
                            break
                    cur = {"ref": "mục " + m2.group(1), "title": plain, "lvl": 2, "blocks": [], "id": m2.group(1)}
                    sections.append(cur)
                    continue
                prefix = "#" * lvl
                cur["blocks"].append("%s %s" % (prefix, text))
            else:
                cur["blocks"].append(b)
        if sections:
            if preface:
                sections[0]["blocks"][:0] = preface + ["# " + sections[0]["raw"]]
        for s in sections:
            if not any(not x.startswith("#") for x in s["blocks"]) and s["lvl"] in (1,) and s["id"] in ("4", "12"):
                continue                      # mục cha chỉ có tiêu đề: không tạo tệp
            name = NAMES.get("%s|%s" % (doc, s["ref"]))
            if not name:
                print("CẢNH BÁO: không có tên tệp cho", doc, s["ref"], file=sys.stderr)
                continue
            head = HEADER.format(doc=doc, ref=s["ref"], src=src)
            text = head + "\n\n# " + s["title"] + "\n\n" + "\n\n".join(s["blocks"]).strip() + "\n"
            written[name] = text
    # INDEX
    idx = ["# Chỉ mục đặc tả (docs/spec)", "",
           "Tệp sinh bởi `scripts/split_spec.py`. Bản chỉ đọc của BRD / SRS / SDD đã đóng băng. "
           "Bảng \"việc nào → tệp nào\" nằm ở `AI_CONTEXT.md` mục 9; hãy mở đúng tệp thay vì cả tài liệu.",
           "", "| Tệp | Nội dung | KB |", "|---|---|---|"]
    for name in sorted(written, key=lambda n: ("brd" not in n, list(NAMES.values()).index(n))):
        t = written[name]
        title = re.search(r"^# (.*)$", t, re.M).group(1).replace("`", "")
        idx.append("| `%s` | %s | %.1f |" % (name, title, len(t.encode("utf-8")) / 1024))
    written["INDEX.md"] = "\n".join(idx) + "\n"
    diff = 0
    for name, text in written.items():
        p = os.path.join(OUT, name)
        old = open(p, encoding="utf-8").read() if os.path.exists(p) else None
        if old != text:
            diff += 1
            print("KHÁC" if old is not None else "MỚI", name)
        if not check:
            open(p, "w", encoding="utf-8", newline="\n").write(text)
    print("%d tệp, %d khác" % (len(written), diff))
    return 1 if (check and diff) else 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
