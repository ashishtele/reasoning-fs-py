#!/usr/bin/env python3
"""Benchmark LMDB (C library, very fast) vs ChromaDB for VFS use case."""

import time
import random
import os
import shutil
import sys
import pickle

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def generate_random_content(size_kb: int = 1) -> str:
    words = ["lorem", "ipsum", "dolor", "sit", "amet"]
    return " ".join(random.choices(words, k=size_kb * 20))


def benchmark_lmdb(num_files: int = 100):
    """Benchmark LMDB."""
    import lmdb
    
    db_path = "tmp_lmdb_benchmark"
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    os.makedirs(db_path, exist_ok=True)
    
    # Generate test data
    test_files = [
        (f"dir{random.randint(0, 9)}/file_{i}.txt", generate_random_content(1))
        for i in range(num_files)
    ]
    
    # Benchmark WRITE
    start = time.perf_counter()
    
    env = lmdb.open(db_path, map_size=1024**3)  # 1GB max
    
    with env.begin(write=True) as txn:
        for path, content in test_files:
            txn.put(path.encode(), pickle.dumps(content))
    
    write_time = (time.perf_counter() - start) * 1000
    env.close()
    
    # Benchmark READ (all files, 3x)
    start = time.perf_counter()
    
    env = lmdb.open(db_path, map_size=1024**3, readonly=True)
    
    for _ in range(3):  # Read 3x
        with env.begin() as txn:
            for path, _ in test_files:
                _ = txn.get(path.encode())
    
    read_time = (time.perf_counter() - start) * 1000
    env.close()
    
    # Cleanup
    shutil.rmtree(db_path)
    
    return write_time, read_time, num_files / (write_time / 1000)


def benchmark_chroma(num_files: int = 100):
    """Benchmark ChromaDB (optimized version)."""
    import chromadb
    from chromadb.config import Settings
    
    db_path = "tmp_chroma_benchmark"
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    
    # Generate test data
    test_files = [
        (f"dir{random.randint(0, 9)}/file_{i}.txt", generate_random_content(1))
        for i in range(num_files)
    ]
    
    client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(anonymized_telemetry=False)
    )
    collection = client.get_or_create_collection(name="files", embedding_function=None)
    
    # Benchmark WRITE (batched)
    start = time.perf_counter()
    
    batch_size = 100
    for i in range(0, len(test_files), batch_size):
        batch = test_files[i:i+batch_size]
        ids = [f"doc_{p[0].replace('/', '_')}" for p in batch]
        docs = [p[1] for p in batch]
        metas = [{"path": p[0]} for p in batch]
        collection.add(ids=ids, documents=docs, metadatas=metas)
    
    write_time = (time.perf_counter() - start) * 1000
    
    # Benchmark READ (all files, 3x, with cache simulation)
    start = time.perf_counter()
    
    cache = {}
    for _ in range(3):
        for path, _ in test_files:
            if path not in cache:
                results = collection.get(where={"path": path}, include=["documents"])
                if results["ids"]:
                    cache[path] = results["documents"][0]
    
    read_time = (time.perf_counter() - start) * 1000
    
    # Cleanup
    client.delete_collection("files")
    shutil.rmtree(db_path)
    
    return write_time, read_time, num_files / (write_time / 1000)


def main():
    print("LMDB (C library) vs ChromaDB Benchmark")
    print("=" * 60)
    print(f"Testing with 100 files, 1KB each\n")
    
    # Benchmark LMDB
    print("[1/2] Benchmarking LMDB...")
    write_lmdb, read_lmdb, tput_lmdb = benchmark_lmdb()
    print(f"   Write: {write_lmdb:.2f}ms, Read: {read_lmdb:.2f}ms, Throughput: {tput_lmdb:.1f} files/sec")
    
    # Benchmark ChromaDB
    print("[2/2] Benchmarking ChromaDB (optimized)...")
    write_chroma, read_chroma, tput_chroma = benchmark_chroma()
    print(f"   Write: {write_chroma:.2f}ms, Read: {read_chroma:.2f}ms, Throughput: {tput_chroma:.1f} files/sec")
    
    # Compare
    print("\n" + "=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(f"Write speedup:  {write_chroma / write_lmdb:.1f}x (LMDB is faster)")
    print(f"Read speedup:   {read_chroma / read_lmdb:.1f}x (LMDB is faster)")
    print(f"Throughput:     {tput_lmdb / tput_chroma:.1f}x (LMDB files/sec / ChromaDB files/sec)")
    
    print(f"\n💡 LMDB is {write_chroma / write_lmdb:.0f}x faster for writes")
    print(f"💡 LMDB is {read_chroma / read_lmdb:.0f}x faster for reads")
    
    # Save results
    import json
    results = {
        "lmdb": {"write_ms": write_lmdb, "read_ms": read_lmdb, "files_per_sec": tput_lmdb},
        "chromadb": {"write_ms": write_chroma, "read_ms": read_chroma, "files_per_sec": tput_chroma}
    }
    
    with open("lmdb_vs_chroma.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📊 Results saved to: lmdb_vs_chroma.json")


if __name__ == "__main__":
    main()
