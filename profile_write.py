#!/usr/bin/env python3
"""Profile write latency in reasoning-fs to identify bottlenecks."""

import time
import tempfile
import shutil
from reasoning_fs.vfs import ChromaFs

def profile_write():
    """Break down write latency into components."""
    temp_db = tempfile.mkdtemp()
    vfs = ChromaFs(db_path=temp_db)
    
    print("\n" + "="*70)
    print("WRITE LATENCY PROFILING")
    print("="*70)
    
    # Test 1: Single file write breakdown
    print("\n[1] SINGLE FILE WRITE BREAKDOWN")
    print("-"*70)
    
    start = time.time()
    content = "SELECT * FROM users WHERE id = 1"
    parse_start = time.time()
    path, content = content.split("=", 1)
    parse_time = (time.time() - parse_start) * 1000
    
    tree_update_start = time.time()
    vfs._path_set.add(path)
    # Build dir path for _dir_map
    parts = path.rsplit("/", 1)
    if len(parts) == 2:
        dir_path, file_name = parts
        if dir_path not in vfs._dir_map:
            vfs._dir_map[dir_path] = []
        vfs._dir_map[dir_path].append(file_name)
    tree_time = (time.time() - tree_update_start) * 1000
    
    embed_start = time.time()
    import hashlib
    hash_int = int(hashlib.md5(content.encode()).hexdigest()[:8], 16)
    embedding = [float(hash_int) / 2**32] * 100
    embed_time = (time.time() - embed_start) * 1000
    
    chroma_start = time.time()
    vfs.collection.add(
        ids=[path],
        documents=[content],
        metadatas=[{"path": path}],
    )
    chroma_time = (time.time() - chroma_start) * 1000
    
    save_tree_start = time.time()
    vfs._save_path_tree()
    save_tree_time = (time.time() - save_tree_start) * 1000
    
    total = (time.time() - start) * 1000
    
    print(f"Parse path/content:     {parse_time:>8.2f} ms")
    print(f"Update in-memory cache: {tree_time:>8.2f} ms")
    print(f"Generate embedding:     {embed_time:>8.2f} ms")
    print(f"ChromaDB add:           {chroma_time:>8.2f} ms")
    print(f"Save __path_tree__:     {save_tree_time:>8.2f} ms")
    print(f"TOTAL:                  {total:>8.2f} ms")
    
    # Test 2: Batch write comparison
    print("\n[2] BATCH WRITE vs SINGLE WRITE")
    print("-"*70)
    
    # Clean and recreate
    shutil.rmtree(temp_db)
    vfs2 = ChromaFs(db_path=temp_db)
    
    # Single writes
    start = time.time()
    for i in range(10):
        vfs2.write(f"file_{i}.txt=content {i}")
    single_total = (time.time() - start) * 1000
    single_avg = single_total / 10
    
    # Clean and recreate
    shutil.rmtree(temp_db)
    vfs3 = ChromaFs(db_path=temp_db)
    
    # Batch write (if we implemented it)
    start = time.time()
    paths = [f"batch_{i}.txt" for i in range(10)]
    contents = [f"batch content {i}" for i in range(10)]
    
    # Manual batch
    batch_add_start = time.time()
    vfs3.collection.add(
        ids=paths,
        documents=contents,
        metadatas=[{"path": p} for p in paths],
    )
    batch_add_time = (time.time() - batch_add_start) * 1000
    
    # Update cache
    cache_update_start = time.time()
    for p, c in zip(paths, contents):
        vfs3._path_set.add(p)
        vfs3._path_cache[p] = c
    cache_time = (time.time() - cache_update_start) * 1000
    
    # Save tree once
    tree_save_start = time.time()
    vfs3._save_path_tree()
    tree_save_time = (time.time() - tree_save_start) * 1000
    
    batch_total = (time.time() - start) * 1000
    batch_avg = batch_total / 10
    
    print(f"Single writes (10x):    {single_total:>8.2f} ms total, {single_avg:>8.2f} ms avg")
    print(f"Batch add:              {batch_add_time:>8.2f} ms")
    print(f"Cache update:           {cache_time:>8.2f} ms")
    print(f"Tree save (once):       {tree_save_time:>8.2f} ms")
    print(f"Batch total (10x):      {batch_total:>8.2f} ms total, {batch_avg:>8.2f} ms avg")
    print(f"SPEEDUP:                {single_avg/batch_avg:.2f}x")
    
    # Test 3: Embedding function overhead
    print("\n[3] EMBEDDING FUNCTION OVERHEAD")
    print("-"*70)
    
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')
    
    content = "SELECT * FROM users WHERE id = 1"
    
    # Warm up
    model.encode([content])
    
    start = time.time()
    for _ in range(10):
        embedding = model.encode([content])
    avg_embed_time = ((time.time() - start) / 10) * 1000
    
    print(f"all-MiniLM-L6-v2:       {avg_embed_time:>8.2f} ms per encoding")
    print(f"Dimension:              {len(embedding[0])}")
    
    shutil.rmtree(temp_db)
    
    print("\n" + "="*70)
    print("BOTTLENECK ANALYSIS")
    print("="*70)
    print(f"1. ChromaDB add: ~{chroma_time:.0f}ms (disk I/O + indexing)")
    print(f"2. Embedding:    ~{avg_embed_time:.0f}ms (if using real embeddings)")
    print(f"3. Tree save:    ~{save_tree_time:.0f}ms (gzip + base64 + ChromaDB)")
    print("\nOPTIMIZATION OPPORTUNITIES:")
    print("- Batch writes instead of individual adds")
    print("- Defer __path_tree__ save (only on ls/find, not every write)")
    print("- Use faster embedding (or skip for simple use cases)")
    print("- Async ChromaDB writes")

if __name__ == "__main__":
    profile_write()
