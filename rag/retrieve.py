"""ค้นคืน chunk ที่เกี่ยวข้องกับคำถาม (เวิร์กช็อป 2 และ 4) ทำงานในเครื่องทั้งหมด ไม่เรียก API

python -m rag.retrieve "คำถาม" -k 4 [--method tfidf|hybrid] [--include-superseded] [--json]
"""
import argparse
import json

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from rag.chunk import chunk_docs


def index_text(chunk: dict) -> str:
    return f"{chunk['title']}\n{chunk['section']}\n{chunk['text']}"


class Retriever:
    def __init__(self, chunks: list[dict] | None = None, method: str = "tfidf"):
        """method="tfidf": TF-IDF ระดับตัวอักษร (W2) · method="hybrid": วิธีที่ปรับปรุงแล้ว (W4)"""
        if method != "tfidf":
            raise NotImplementedError(f"method={method!r} ยังไม่รองรับ (hybrid ทำใน W4)")
        self.method = method
        self.chunks = chunk_docs() if chunks is None else chunks
        # ภาษาไทยไม่เว้นวรรคระหว่างคำ จึงใช้ n-gram ระดับตัวอักษรแทนการตัดคำ
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.matrix = self.vectorizer.fit_transform([index_text(c) for c in self.chunks])

    def search(self, query: str, k: int = 4, include_superseded: bool = True) -> list[dict]:
        """คืน chunk k อันที่คะแนนสูงสุด เรียงจากมากไปน้อย แต่ละอันเพิ่มช่อง "score" """
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        order = sorted(range(len(self.chunks)), key=lambda i: scores[i], reverse=True)
        results = []
        for i in order:
            chunk = self.chunks[i]
            if not include_superseded and chunk["status"] != "active":
                continue
            results.append({**chunk, "score": float(scores[i])})
            if len(results) == k:
                break
        return results


def main(argv: list[str] | None = None):
    p = argparse.ArgumentParser(description="ค้นคืน chunk ที่เกี่ยวข้องกับคำถาม")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=4)
    p.add_argument("--method", default="tfidf", choices=["tfidf", "hybrid"])
    p.add_argument("--include-superseded", action="store_true", help="รวมเอกสารฉบับเก่าในผลลัพธ์")
    p.add_argument("--json", action="store_true", help="พิมพ์ผลเป็น JSON")
    args = p.parse_args(argv)

    res = Retriever(method=args.method).search(args.query, k=args.k, include_superseded=args.include_superseded)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    for r in res:
        print(f"{r['score']:.3f}  {r['chunk_id']:14s} [{r['status']}] {r['title']} · {r['section']}")
        print("        " + r["text"].splitlines()[-1][:100])


if __name__ == "__main__":
    main()
