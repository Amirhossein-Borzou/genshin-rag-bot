#!/usr/bin/env python3
"""Phase 4: build the semantic (vector) index alongside FTS5.
Embeds every kb chunk (title+header+body) with fastembed BAAI/bge-small-en-v1.5 (384d)
into a vec0 virtual table using sqlite-vec. Incremental: only new chunk_ids get embedded."""
import json
import os
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.abspath(os.path.join(HERE, "..", "data", "kb.sqlite"))
MODEL = "BAAI/bge-small-en-v1.5"


def main():
    import sqlite_vec  # registers vec0 virtual table
    from fastembed import TextEmbedding

    con = sqlite3.connect(DB)
    con.enable_load_extension(True)
    sqlite_vec.load(con)
    con.enable_load_extension(False)

    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(chunk_id TEXT PRIMARY KEY, embedding float[384])")
    con.execute("CREATE TABLE IF NOT EXISTS vec_meta(dim INTEGER, model TEXT, built_at TEXT)")

    done = {r[0] for r in con.execute("SELECT chunk_id FROM vec_chunks")}
    todo = [(t, f"{t}\n{n}\n{h}\n{b}") for t, n, h, b in con.execute("SELECT title, name, header, body FROM kb")]
    todo = [(t, txt) for t, txt in todo if t not in done]
    print(f"chunks: {len(done)} embedded, {len(todo)} to embed")

    if todo:
        model = TextEmbedding(MODEL)
        texts = [txt for _, txt in todo]
        ids = [t for t, _ in todo]
        t0 = time.time()
        B = 32
        for i in range(0, len(texts), B):
            batch = texts[i:i + B]
            for cid, emb in zip(ids[i:i + B], model.embed(batch)):
                con.execute(
                    "INSERT OR REPLACE INTO vec_chunks VALUES (?, ?)",
                    (cid, sqlite_vec.serialize_float32(emb.tolist())),
                )
        con.execute("INSERT OR REPLACE INTO vec_meta VALUES (384, ?, ?)", (MODEL, time.strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()
        print(f"embedded {len(todo)} in {time.time()-t0:.0f}s")

    n = con.execute("SELECT count(*) FROM vec_chunks").fetchone()[0]
    size_mb = os.path.getsize(DB) / 1e6
    print(f"vec_chunks: {n} | db size now {size_mb:.0f}MB")
    con.close()


if __name__ == "__main__":
    main()
