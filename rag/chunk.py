"""แบ่งเอกสารเป็น chunk พร้อม metadata (เวิร์กช็อป 1)

แต่ละ chunk เป็น dict ที่มีอย่างน้อย:
chunk_id ("<doc_id>#<ลำดับ>"), doc_id, title, section, status, effective_date, text
"""
from rag.ingest import load_docs

MAX_CHARS = 600


def split_sections(body: str) -> list[tuple[str, str]]:
    """แยกเนื้อหาเป็น (ชื่อหัวข้อ, เนื้อหา) ตามหัวข้อ ## ข้ามบรรทัดหัวเรื่อง # และเนื้อหาว่าง"""
    sections, name, lines = [], "", []
    for line in body.splitlines():
        if line.startswith("## "):
            sections.append((name, "\n".join(lines).strip()))
            name, lines = line[3:].strip(), []
        elif not line.startswith("# "):
            lines.append(line)
    sections.append((name, "\n".join(lines).strip()))
    return [(n, t) for n, t in sections if t]


def pack_lines(text: str, budget: int) -> list[str]:
    """รวมบรรทัดเป็นก้อนละไม่เกิน budget ตัวอักษร บรรทัดที่ยาวเกินจะถูกตัดตามจำนวนตัวอักษร"""
    pieces, current = [], ""
    for line in text.splitlines():
        while len(line) > budget:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:budget])
            line = line[budget:]
        if current and len(current) + 1 + len(line) > budget:
            pieces.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current.strip():
        pieces.append(current)
    return pieces


def chunk_docs(docs: list[dict] | None = None, max_chars: int = MAX_CHARS) -> list[dict]:
    docs = load_docs() if docs is None else docs
    chunks = []
    for doc in docs:
        meta = {k: v for k, v in doc.items() if k not in {"body", "path"}}
        n = 0
        for section, text in split_sections(doc["body"]):
            # ใส่หัวข้อไว้ในข้อความด้วย เพื่อให้คำในหัวข้อช่วยการค้นคืน
            header = f"{doc['title']} · {section}\n" if section else f"{doc['title']}\n"
            for piece in pack_lines(text, max_chars - len(header)):
                n += 1
                chunks.append({
                    **meta,
                    "chunk_id": f"{doc['doc_id']}#{n}",
                    "section": section,
                    "path": doc.get("path", ""),
                    "text": header + piece,
                })
    return chunks


if __name__ == "__main__":
    cs = chunk_docs()
    print(len(cs), "chunks · ยาวสุด", max(len(c["text"]) for c in cs), "ตัวอักษร")
