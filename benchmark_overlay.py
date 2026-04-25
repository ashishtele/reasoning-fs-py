#!/usr/bin/env python3
"""Benchmark OverlayFs vs pure ChromaFs."""

import time
import tempfile
import shutil
from reasoning_fs.vfs import ChromaFs
from reasoning_fs.overlay import OverlayFs


def benchmark_chromafs(num_files: int = 100):
    """Benchmark pure ChromaFs."""
    temp_db = tempfile.mkdtemp()
    vfs = ChromaFs(db_path=temp_db)
    
    # Write
    start = time.time()
    for i in range(num_files):
        vfs.write(f"test/file_{i}.txt=content {i}")
    write_time = (time.time() - start) * 1000
    
    # Read
    start = time.time()
    for i in range(num_files):
        vfs.read(f"test/file_{i}.txt")
    read_time = (time.time() - start) * 1000
    
    shutil.rmtree(temp_db)
    
    return write_time, read_time


def benchmark_overlayfs(num_files: int = 100, batch_size: int = 1000):
    """Benchmark OverlayFs."""
    temp_db = tempfile.mkdtemp()
    vfs = OverlayFs(db_path=temp_db, batch_size=batch_size, auto_sync=False)
    
    # Write (memory only, no auto-sync)
    start = time.time()
    for i in range(num_files):
        vfs.write(f"test/file_{i}.txt=content {i}")
    write_time = (time.time() - start) * 1000
    
    # Sync to disk
    start = time.time()
    vfs.sync()
    sync_time = (time.time() - start) * 1000
    
    # Read (from cache)
    start = time.time()
    for i in range(num_files):
        vfs.read(f"test/file_{i}.txt")
    read_time = (time.time() - start) * 1000
    
    shutil.rmtree(temp_db)
    
    return write_time, sync_time, read_time


def main():
    num_files = 100
    
    print("="*70)
    print("OverlayFs vs ChromaFs Benchmark")
    print("="*70)
    
    # ChromaFs
    print(f"\n[1] ChromaFs ({num_files} files)")
    print("-" * 70)
    cf_write, cf_read = benchmark_chromafs(num_files)
    print(f"Write time:    {cf_write:.2f} ms ({cf_write/num_files:.2f} ms/file)")
    print(f"Read time:     {cf_read:.2f} ms ({cf_read/num_files:.2f} ms/file)")
    print(f"Total:         {cf_write + cf_read:.2f} ms")
    
    # OverlayFs
    print(f"\n[2] OverlayFs ({num_files} files, batch={num_files})")
    print("-" * 70)
    of_write, of_sync, of_read = benchmark_overlayfs(num_files, batch_size=num_files)
    print(f"Write time:    {of_write:.4f} ms ({of_write/num_files:.6f} ms/file) [memory]")
    print(f"Sync time:     {of_sync:.2f} ms ({of_sync/num_files:.2f} ms/file) [batched]")
    print(f"Read time:     {of_read:.4f} ms ({of_read/num_files:.6f} ms/file)")
    print(f"Total:         {of_write + of_sync + of_read:.2f} ms")
    
    # Comparison
    print("\n" + "="*70)
    print("SPEEDUP")
    print("="*70)
    write_speedup = cf_write / of_write if of_write > 0 else float('inf')
    total_speedup = (cf_write + cf_read) / (of_write + of_sync + of_read)
    print(f"Write speedup:   {write_speedup:.1f}x faster")
    print(f"Total speedup:   {total_speedup:.1f}x faster")
    print(f"\nNote: OverlayFs trades per-write latency for batched sync.")
    print(f"Best for: Agents that write many files, then read frequently.")


if __name__ == "__main__":
    main()
