"""ค้นคืน chunk ที่เกี่ยวข้องกับคำถาม (เวิร์กช็อป 2 และ 4) ทำงานในเครื่องทั้งหมด ไม่เรียก API

python -m rag.retrieve "คำถาม" -k 4 [--method tfidf|hybrid] [--include-superseded] [--json]
"""
import argparse
import json

import numpy as np
from pythainlp.corpus import thai_stopwords
from pythainlp.tokenize import word_tokenize
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from rag.chunk import chunk_docs

# คำพ้องสำหรับขยายคำค้น (W4) สร้างจากคำถามชุด dev ที่ค้นพลาดเท่านั้น
# key คือคำที่ผู้ใช้พิมพ์ value คือคำที่เอกสารบริษัทใช้
SYNONYMS = {
    "อีวี": "รถยนต์ไฟฟ้า จุดชาร์จ",
    "เสียบชาร์จ": "จุดชาร์จ",
    "ลืมรหัสผ่าน": "รีเซ็ต Self-Service Password",
    "ค่าน้ำมัน": "การใช้รถส่วนตัว กิโลเมตรละ",
}

STOPWORDS = frozenset(thai_stopwords())
HYBRID_WEIGHT_BM25 = 0.2


def index_text(chunk: dict) -> str:
    return f"{chunk['title']}\n{chunk['section']}\n{chunk['text']}"


def tokenize(text: str) -> list[str]:
    """ตัดคำด้วย pythainlp (newmm) ตัดช่องว่าง เครื่องหมาย และ stopword ออก"""
    tokens = word_tokenize(text.lower(), engine="newmm", keep_whitespace=False)
    return [t for t in tokens if t.strip() and t not in STOPWORDS and any(ch.isalnum() for ch in t)]


def expand_query(query: str) -> str:
    q = query.lower()
    extra = [v for k, v in SYNONYMS.items() if k in q]
    return " ".join([query, *extra])


def normalize(scores: np.ndarray) -> np.ndarray:
    top = scores.max()
    return scores / top if top > 0 else scores


class Retriever:
    def __init__(self, chunks: list[dict] | None = None, method: str = "tfidf"):
        """method="tfidf": TF-IDF ระดับตัวอักษร (W2) · method="hybrid": วิธีที่ปรับปรุงแล้ว (W4)"""
        if method not in {"tfidf", "hybrid"}:
            raise ValueError(f"ไม่รู้จัก method={method!r}")
        self.method = method
        self.chunks = chunk_docs() if chunks is None else chunks
        texts = [index_text(c) for c in self.chunks]
        # ภาษาไทยไม่เว้นวรรคระหว่างคำ จึงใช้ n-gram ระดับตัวอักษรแทนการตัดคำ
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.matrix = self.vectorizer.fit_transform(texts)
        if method == "hybrid":
            self.bm25 = BM25Okapi([tokenize(t) for t in texts])

    def scores(self, query: str) -> np.ndarray:
        if self.method == "tfidf":
            return cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        query = expand_query(query)
        tfidf = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        bm25 = self.bm25.get_scores(tokenize(query))
        # ปรับสเกลแต่ละวิธีให้คะแนนสูงสุดเป็น 1 ก่อนรวม
        return (1 - HYBRID_WEIGHT_BM25) * normalize(tfidf) + HYBRID_WEIGHT_BM25 * normalize(bm25)

    def search(self, query: str, k: int = 4, include_superseded: bool = True) -> list[dict]:
        """คืน chunk k อันที่คะแนนสูงสุด เรียงจากมากไปน้อย แต่ละอันเพิ่มช่อง "score" """
        scores = self.scores(query)
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
    p.add_argument("--include-superseded", action="store_true", help="รวมเอกสารฉบับเก่าในผลลัพธ์ (ค่าเริ่มต้นกรองออก)")
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
