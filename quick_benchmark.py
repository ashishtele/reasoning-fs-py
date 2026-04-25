"""Quick benchmark of enhanced VFS features."""

import time
from lmdb_vfs.enhanced import EnhancedVFS

def quick_benchmark():
    print("=== Quick Enhanced VFS Benchmark ===\n")
    
    vfs = EnhancedVFS("/tmp/quick_benchmark.lmdb", map_size=1*1024**3)
    
    # 1. Sandboxes
    print("1. Copy-on-Write Sandboxes:")
    start = time.perf_counter()
    sid = vfs.create_sandbox("test")
    print(f"   - Create sandbox: {(time.perf_counter()-start)*1000:.1f}ms")
    
    start = time.perf_counter()
    vfs.sandbox_write("test.txt", "Hello" * 100)
    print(f"   - Sandbox write: {(time.perf_counter()-start)*1000:.1f}ms")
    
    start = time.perf_counter()
    vfs.revert_sandbox()
    print(f"   - Revert sandbox: {(time.perf_counter()-start)*1000:.1f}ms")
    
    # 2. Tiered access
    print("\n2. Tiered Access (L0/L1/L2):")
    content = "Line\n" * 1000
    start = time.perf_counter()
    vfs.write_tiered("tiered.txt", content, "Summary", "Overview\n" + "\n".join(content.split("\n")[:10]))
    print(f"   - Write tiered: {(time.perf_counter()-start)*1000:.1f}ms")
    
    for level in ["L0", "L1", "L2"]:
        start = time.perf_counter()
        _ = vfs.read_tiered("tiered.txt", level)
        print(f"   - Read {level}: {(time.perf_counter()-start)*1000:.3f}ms")
    
    # 3. Versioning
    print("\n3. Versioning:")
    start = time.perf_counter()
    v1 = vfs.write_versioned("versioned.txt", "v1 content", "First version")
    v2 = vfs.write_versioned("versioned.txt", "v2 content", "Second version")
    print(f"   - 2 versioned writes: {(time.perf_counter()-start)*1000:.1f}ms")
    
    start = time.perf_counter()
    history = vfs.get_version_history("versioned.txt")
    print(f"   - Get history: {(time.perf_counter()-start)*1000:.1f}ms ({len(history)} versions)")
    
    vfs.close()
    print("\n✓ All features working!")

if __name__ == "__main__":
    quick_benchmark()
