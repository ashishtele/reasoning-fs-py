#!/usr/bin/env python3
"""Benchmark ChromaDB optimizations: Original vs Optimized.

Tests:
1. Write 100 files (batch vs individual)
2. Read 100 files (cached vs DB lookup)
3. Grep across all files
4. Find files by pattern

Expected improvements:
- Write: 3-5x faster (batching)
- Read: 10-20x faster (no embeddings + cache)
- Grep: 2-3x faster (no embedding overhead)
"""

import time
import random
import string
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reasoning_fs.vfs import ChromaFs as OptimizedChromaFs
from reasoning_fs.vfs_backup import ChromaFs as OriginalChromaFs


def generate_random_content(size_kb: int = 1) -> str:
    """Generate random text content."""
    words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", 
             "adipiscing", "elit", "sed", "do", "eiusmod", "tempor"]
    content = []
    target_size = size_kb * 1024
    
    while len(" ".join(content)) < target_size:
        content.append(random.choice(words))
    
    return " ".join(content)


def benchmark_write(vfs, num_files: int = 100, size_kb: int = 1) -> float:
    """Benchmark writing files."""
    start = time.perf_counter()
    
    for i in range(num_files):
        path = f"dir{random.randint(0, 9)}/file_{i}.txt"
        content = generate_random_content(size_kb)
        vfs.write(f"{path}={content}")
    
    # Flush any pending writes
    if hasattr(vfs, 'flush'):
        vfs.flush()
    
    end = time.perf_counter()
    return end - start


def benchmark_read(vfs, num_files: int = 100) -> float:
    """Benchmark reading files."""
    # Get list of files
    files = vfs.find("*.txt").split("\n")
    files = [f for f in files if f]  # Filter empty
    
    start = time.perf_counter()
    
    for path in files[:num_files]:
        try:
            content = vfs.cat(path)
            assert len(content) > 0
        except FileNotFoundError:
            pass  # File might not exist
    
    end = time.perf_counter()
    return end - start


def benchmark_grep(vfs, pattern: str = "lorem") -> float:
    """Benchmark grep operation."""
    start = time.perf_counter()
    result = vfs.grep(pattern)
    end = time.perf_counter()
    return end - start


def benchmark_find(vfs, pattern: str = "*.py") -> float:
    """Benchmark find operation."""
    start = time.perf_counter()
    result = vfs.find(pattern)
    end = time.perf_counter()
    return end - start


def run_benchmark(name: str, vfs_class, num_files: int = 100):
    """Run full benchmark suite."""
    print(f"\n{'='*60}")
    print(f"Benchmark: {name}")
    print(f"{'='*60}")
    
    # Clean up any existing DB
    db_path = f"benchmark_{name.lower().replace(' ', '_')}_db"
    import shutil
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    
    # Initialize
    print(f"Initializing {name}...")
    vfs = vfs_class(db_path=db_path)
    
    results = {}
    
    # Test 1: Write
    print(f"\n1. Writing {num_files} files...")
    write_time = benchmark_write(vfs, num_files=num_files)
    results["write"] = write_time
    print(f"   Time: {write_time*1000:.2f}ms ({num_files/write_time:.0f} files/sec)")
    
    # Test 2: Read
    print(f"\n2. Reading {num_files} files...")
    read_time = benchmark_read(vfs, num_files=num_files)
    results["read"] = read_time
    print(f"   Time: {read_time*1000:.2f}ms ({num_files/read_time:.0f} files/sec)")
    
    # Test 3: Grep
    print(f"\n3. Grep for 'lorem'...")
    grep_time = benchmark_grep(vfs, "lorem")
    results["grep"] = grep_time
    print(f"   Time: {grep_time*1000:.2f}ms")
    
    # Test 4: Find
    print(f"\n4. Find '*.txt' files...")
    find_time = benchmark_find(vfs, "*.txt")
    results["find"] = find_time
    print(f"   Time: {find_time*1000:.2f}ms")
    
    # Cleanup
    shutil.rmtree(db_path)
    
    return results


def main():
    """Run benchmarks and compare."""
    print("ChromaDB Optimization Benchmark")
    print("=" * 60)
    
    num_files = 100
    
    # Run benchmarks
    original_results = run_benchmark("Original", OriginalChromaFs, num_files)
    optimized_results = run_benchmark("Optimized", OptimizedChromaFs, num_files)
    
    # Compare
    print(f"\n{'='*60}")
    print("COMPARISON")
    print(f"{'='*60}")
    
    print(f"\n{'Operation':<15} {'Original':<15} {'Optimized':<15} {'Speedup':<10}")
    print("-" * 60)
    
    for op in ["write", "read", "grep", "find"]:
        orig_time = original_results[op] * 1000
        opt_time = optimized_results[op] * 1000
        speedup = orig_time / opt_time if opt_time > 0 else float('inf')
        print(f"{op:<15} {orig_time:>10.2f}ms   {opt_time:>10.2f}ms   {speedup:>8.2f}x")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    avg_speedup = sum(original_results[op] / optimized_results[op] 
                     for op in ["write", "read", "grep", "find"] 
                     if optimized_results[op] > 0) / 4
    print(f"\nAverage speedup: {avg_speedup:.2f}x")
    print(f"Write improvement: {original_results['write'] / optimized_results['write']:.2f}x")
    print(f"Read improvement: {original_results['read'] / optimized_results['read']:.2f}x")
    
    # Verify correctness
    print(f"\n{'='*60}")
    print("VERIFICATION")
    print(f"{'='*60}")
    
    # Test that optimized version works correctly
    db_path = "verify_db"
    if os.path.exists(db_path):
        import shutil
        shutil.rmtree(db_path)
    
    vfs = OptimizedChromaFs(db_path=db_path)
    vfs.write("test/file1.py=print('hello')")
    vfs.write("test/file2.py=print('world')")
    vfs.flush()
    
    content1 = vfs.cat("test/file1.py")
    content2 = vfs.cat("test/file2.py")
    
    assert content1 == "print('hello')", f"Expected 'print('hello')', got '{content1}'"
    assert content2 == "print('world')", f"Expected 'print('world')', got '{content2}'"
    
    grep_result = vfs.grep("hello")
    assert "test/file1.py" in grep_result, "Grep failed to find 'hello'"
    
    find_result = vfs.find("*.py")
    assert "test/file1.py" in find_result, "Find failed to find *.py files"
    
    print("✓ All correctness tests passed!")
    
    # Cleanup
    import shutil
    shutil.rmtree(db_path)
    
    print(f"\nBenchmark complete!")


if __name__ == "__main__":
    main()
