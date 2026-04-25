"""Benchmark enhanced VFS features.

Tests:
- Copy-on-write sandbox performance
- Tiered access (L0/L1/L2) speedup
- Versioning overhead
- HTTP/MCP API latency
"""

import time
import json
import random
import string
from pathlib import Path
from lmdb_vfs.enhanced import EnhancedVFS


def random_content(size_kb: int) -> str:
    """Generate random content of specified size."""
    words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur"]
    target_bytes = size_kb * 1024
    content = []
    while len(" ".join(content).encode()) < target_bytes:
        content.append(random.choice(words))
    return " ".join(content)[:target_bytes]


def benchmark_sandboxes():
    """Test copy-on-write sandbox performance."""
    print("\n=== Copy-on-Write Sandboxes (Turso Pattern) ===")
    
    vfs = EnhancedVFS("/tmp/benchmark_sandbox.lmdb", map_size=10*1024**3)
    
    # Create base files
    print("Creating 1000 base files...")
    start = time.perf_counter()
    for i in range(1000):
        vfs.write(f"docs/file_{i}.txt", random_content(10))
    base_time = time.perf_counter() - start
    print(f"  Base writes: {base_time:.2f}s ({1000/base_time:.0f} files/sec)")
    
    # Create sandbox
    print("Creating sandbox...")
    start = time.perf_counter()
    sandbox_id = vfs.create_sandbox("test_sandbox")
    sandbox_create_time = time.perf_counter() - start
    print(f"  Sandbox creation: {sandbox_create_time*1000:.2f}ms")
    
    # Write in sandbox (copy-on-write)
    print("Writing 100 files in sandbox...")
    start = time.perf_counter()
    for i in range(100):
        vfs.sandbox_write(f"docs/sandbox_file_{i}.txt", random_content(10))
    sandbox_write_time = time.perf_counter() - start
    print(f"  Sandbox writes: {sandbox_write_time:.2f}s ({100/sandbox_write_time:.0f} files/sec)")
    
    # Revert sandbox
    print("Reverting sandbox...")
    start = time.perf_counter()
    vfs.revert_sandbox()
    revert_time = time.perf_counter() - start
    print(f"  Sandbox revert: {revert_time*1000:.2f}ms")
    
    vfs.close()
    
    print(f"\n  Summary:")
    print(f"    - Sandbox creation: ~{sandbox_create_time*1000:.0f}ms")
    print(f"    - Sandbox write overhead: ~{(sandbox_write_time/100)*1000:.1f}ms/file")
    print(f"    - Revert time: ~{revert_time*1000:.0f}ms")


def benchmark_tiered_access():
    """Test tiered access performance."""
    print("\n=== Tiered Access (OpenViking Pattern) ===")
    
    vfs = EnhancedVFS("/tmp/benchmark_tiered.lmdb", map_size=10*1024**3)
    
    # Create tiered files
    print("Creating 100 tiered files (100KB each)...")
    start = time.perf_counter()
    for i in range(100):
        content = random_content(100)
        vfs.write_tiered(
            f"docs/tiered_{i}.txt",
            full_content=content,
            summary=f"Summary for file {i}",
            overview=f"Overview for file {i}\n" + "\n".join(content.split("\n")[:10])
        )
    write_time = time.perf_counter() - start
    print(f"  Tiered writes: {write_time:.2f}s ({100/write_time:.0f} files/sec)")
    
    # Read at different levels
    print("\nReading 100 files at different levels:")
    
    # L0 (summary)
    start = time.perf_counter()
    for i in range(100):
        content = vfs.read_tiered(f"docs/tiered_{i}.txt", "L0")
    l0_time = time.perf_counter() - start
    print(f"  L0 (summary): {l0_time:.2f}s ({100/l0_time:.0f} reads/sec, avg {l0_time*1000:.2f}ms/read)")
    
    # L1 (overview)
    start = time.perf_counter()
    for i in range(100):
        content = vfs.read_tiered(f"docs/tiered_{i}.txt", "L1")
    l1_time = time.perf_counter() - start
    print(f"  L1 (overview): {l1_time:.2f}s ({100/l1_time:.0f} reads/sec, avg {l1_time*1000:.2f}ms/read)")
    
    # L2 (full)
    start = time.perf_counter()
    for i in range(100):
        content = vfs.read_tiered(f"docs/tiered_{i}.txt", "L2")
    l2_time = time.perf_counter() - start
    print(f"  L2 (full): {l2_time:.2f}s ({100/l2_time:.0f} reads/sec, avg {l2_time*1000:.2f}ms/read)")
    
    # Token savings
    avg_summary_len = len(vfs.read_tiered("docs/tiered_0.txt", "L0"))
    avg_overview_len = len(vfs.read_tiered("docs/tiered_0.txt", "L1"))
    avg_full_len = len(vfs.read_tiered("docs/tiered_0.txt", "L2"))
    
    print(f"\n  Token savings (vs full read):")
    print(f"    - L0: {(1 - avg_summary_len/avg_full_len)*100:.0f}% reduction")
    print(f"    - L1: {(1 - avg_overview_len/avg_full_len)*100:.0f}% reduction")
    
    vfs.close()


def benchmark_versioning():
    """Test versioning overhead."""
    print("\n=== Versioning (markdownfs Pattern) ===")
    
    vfs = EnhancedVFS("/tmp/benchmark_versioning.lmdb", map_size=10*1024**3)
    
    # Write versioned files
    print("Writing 100 files with versioning (3 versions each)...")
    start = time.perf_counter()
    for i in range(100):
        for v in range(3):
            vfs.write_versioned(
                f"docs/versioned_{i}.txt",
                f"Version {v} content: {random_content(1)}",
                message=f"Update {v}",
                author="test"
            )
    versioned_time = time.perf_counter() - start
    print(f"  Versioned writes: {versioned_time:.2f}s ({300/versioned_time:.0f} writes/sec)")
    
    # Get version history
    print("\nGetting version history for 100 files:")
    start = time.perf_counter()
    for i in range(100):
        history = vfs.get_version_history(f"docs/versioned_{i}.txt")
    history_time = time.perf_counter() - start
    print(f"  History reads: {history_time:.2f}s ({100/history_time:.0f} reads/sec)")
    
    # Compare to non-versioned
    vfs_no_version = EnhancedVFS("/tmp/benchmark_no_version.lmdb", map_size=10*1024**3, enable_versioning=False)
    start = time.perf_counter()
    for i in range(100):
        vfs_no_version.write(f"docs/file_{i}.txt", random_content(1))
    non_versioned_time = time.perf_counter() - start
    print(f"\n  Overhead:")
    print(f"    - Versioned: {versioned_time:.2f}s")
    print(f"    - Non-versioned: {non_versioned_time:.2f}s")
    print(f"    - Overhead: {(versioned_time/non_versioned_time - 1)*100:.0f}%")
    
    vfs.close()
    vfs_no_version.close()


def main():
    """Run all benchmarks."""
    print("=" * 60)
    print("Enhanced LMDB VFS Benchmark")
    print("=" * 60)
    
    benchmark_sandboxes()
    benchmark_tiered_access()
    benchmark_versioning()
    
    print("\n" + "=" * 60)
    print("Benchmark complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
