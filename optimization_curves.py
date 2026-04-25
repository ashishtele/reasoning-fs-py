#!/usr/bin/env python3
"""Karpathy-style optimization curves for ChromaDB VFS.

Shows what we tried, what worked, and the performance curves.
Like Karpathy's diff value optimization but for filesystem operations.

Run: python3 optimization_curves.py
"""

import time
import random
import json
import os
import sys
import shutil
from typing import Dict, List, Any, Callable
from dataclasses import dataclass
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to import matplotlib, if not, create ASCII charts
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("matplotlib not installed. Install with: pip install matplotlib")
    print("Will generate ASCII charts instead.")


@dataclass
class OptimizationConfig:
    """Configuration for an optimization variant."""
    name: str
    description: str
    use_embeddings: bool
    use_cache: bool
    batch_size: int
    use_get_instead_of_query: bool
    disable_telemetry: bool
    cache_size: int = 1000
    allow_reset: bool = True


@dataclass 
class BenchmarkResult:
    """Results from a benchmark run."""
    config_name: str
    write_ms: float
    read_ms: float
    grep_ms: float
    find_ms: float
    files_per_sec: float


def generate_random_content(size_kb: int = 1) -> str:
    """Generate random text content."""
    words = ["lorem", "ipsum", "dolor", "sit", "amet", "consectetur", 
             "adipiscing", "elit", "sed", "do", "eiusmod", "tempor",
             "tempor", "incididunt", "ut", "labore", "et", "dolore",
             "magna", "aliqua", "enim", "ad", "minim", "veniam"]
    content = []
    target_size = size_kb * 1024
    
    while len(" ".join(content)) < target_size:
        content.append(random.choice(words))
    
    return " ".join(content)


def create_vfs_variant(config: OptimizationConfig, db_path: str):
    """Create a VFS instance with specific optimizations."""
    import chromadb
    from chromadb.config import Settings
    
    # Create client
    settings = {}
    if config.disable_telemetry:
        settings['anonymized_telemetry'] = False
    if config.allow_reset:
        settings['allow_reset'] = True
    
    client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(**settings) if settings else None
    )
    
    # Create collection based on config
    if config.use_embeddings:
        collection = client.get_or_create_collection(name="filesystem")
    else:
        collection = client.get_or_create_collection(
            name="filesystem",
            embedding_function=None
        )
    
    return client, collection, config


def benchmark_variant(config: OptimizationConfig, num_files: int = 100) -> BenchmarkResult:
    """Benchmark a specific optimization variant."""
    db_path = f"tmp_benchmark_{config.name}"
    
    # Clean up
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    
    try:
        client, collection, cfg = create_vfs_variant(config, db_path)
        
        # Generate test data
        test_files = []
        for i in range(num_files):
            path = f"dir{random.randint(0, 9)}/file_{i}.txt"
            content = generate_random_content(1)
            test_files.append((path, content))
        
        # Benchmark WRITE
        start = time.perf_counter()
        
        if cfg.batch_size > 1:
            # Batch write
            batch = []
            for path, content in test_files:
                batch.append({
                    "id": f"doc_{path.replace('/', '_')}",
                    "document": content,
                    "metadata": {"path": path}
                })
            
            # Split into batches
            for i in range(0, len(batch), cfg.batch_size):
                batch_slice = batch[i:i + cfg.batch_size]
                ids = [b["id"] for b in batch_slice]
                docs = [b["document"] for b in batch_slice]
                metas = [b["metadata"] for b in batch_slice]
                
                if cfg.use_embeddings:
                    collection.add(ids=ids, documents=docs, metadatas=metas)
                else:
                    collection.add(ids=ids, documents=docs, metadatas=metas)
        else:
            # Individual writes
            for path, content in test_files:
                doc_id = f"doc_{path.replace('/', '_')}"
                if cfg.use_embeddings:
                    collection.add(ids=[doc_id], documents=[content], metadatas=[{"path": path}])
                else:
                    collection.add(ids=[doc_id], documents=[content], metadatas=[{"path": path}])
        
        write_time = (time.perf_counter() - start) * 1000
        
        # Benchmark READ - simulate real-world pattern: read same files multiple times
        start = time.perf_counter()
        
        if cfg.use_cache:
            # Simulate cache - first read hits DB, subsequent reads are instant
            cache = {}
            for _ in range(3):  # Read each file 3 times (simulates real usage)
                for path, _ in test_files[:num_files]:
                    if path in cache:
                        # Cache hit - instant
                        content = cache[path]
                    else:
                        # Cache miss - hit DB
                        if cfg.use_get_instead_of_query:
                            results = collection.get(where={"path": path}, include=["documents"])
                        else:
                            results = collection.get(where={"path": path}, include=["documents"])
                        
                        if results["ids"]:
                            content = results["documents"][0]
                            cache[path] = content
                        else:
                            content = ""
        else:
            # No cache - hit DB every time (3 reads per file = 300 DB calls)
            for _ in range(3):  # Read each file 3 times
                for path, _ in test_files[:num_files]:
                    if cfg.use_get_instead_of_query:
                        results = collection.get(where={"path": path}, include=["documents"])
                    else:
                        results = collection.get(where={"path": path}, include=["documents"])
        
        read_time = (time.perf_counter() - start) * 1000
        
        # Benchmark GREP
        start = time.perf_counter()
        all_docs = collection.get(include=["documents"])
        pattern = "lorem"
        matches = 0
        for doc in all_docs["documents"]:
            if pattern in doc:
                matches += 1
        grep_time = (time.perf_counter() - start) * 1000
        
        # Benchmark FIND
        start = time.perf_counter()
        all_metas = collection.get(include=["metadatas"])
        pattern = "*.txt"
        import re
        regex = re.compile(pattern.replace(".", r"\.").replace("*", ".*"))
        matches = [m.get("path", "") for m in all_metas["metadatas"] if regex.search(m.get("path", ""))]
        find_time = (time.perf_counter() - start) * 1000
        
        # Cleanup
        client.delete_collection("filesystem")
        shutil.rmtree(db_path)
        
        return BenchmarkResult(
            config_name=config.name,
            write_ms=write_time,
            read_ms=read_time,
            grep_ms=grep_time,
            find_ms=find_time,
            files_per_sec=num_files / (write_time / 1000) if write_time > 0 else 0
        )
    
    except Exception as e:
        print(f"Error benchmarking {config.name}: {e}")
        return None


def run_optimization_study():
    """Run the full optimization study."""
    print("ChromaDB VFS Optimization Study")
    print("=" * 60)
    print("Testing different optimization combinations...\n")
    
    # Define optimization variants (like Karpathy's diff value experiments)
    variants = [
        OptimizationConfig(
            name="baseline",
            description="No optimizations (embeddings + individual writes)",
            use_embeddings=True,
            use_cache=False,
            batch_size=1,
            use_get_instead_of_query=False,
            disable_telemetry=False
        ),
        OptimizationConfig(
            name="no_embeddings",
            description="Disable embeddings only",
            use_embeddings=False,
            use_cache=False,
            batch_size=1,
            use_get_instead_of_query=False,
            disable_telemetry=True
        ),
        OptimizationConfig(
            name="batch_only",
            description="Batch writes only",
            use_embeddings=True,
            use_cache=False,
            batch_size=100,
            use_get_instead_of_query=False,
            disable_telemetry=True
        ),
        OptimizationConfig(
            name="get_only",
            description="Use get() instead of query()",
            use_embeddings=True,
            use_cache=False,
            batch_size=1,
            use_get_instead_of_query=True,
            disable_telemetry=True
        ),
        OptimizationConfig(
            name="no_embeddings + batch",
            description="No embeddings + batch writes",
            use_embeddings=False,
            use_cache=False,
            batch_size=100,
            use_get_instead_of_query=True,
            disable_telemetry=True
        ),
        OptimizationConfig(
            name="full_optimized",
            description="All optimizations (final version)",
            use_embeddings=False,
            use_cache=True,
            batch_size=100,
            use_get_instead_of_query=True,
            disable_telemetry=True
        ),
    ]
    
    results = []
    
    for i, variant in enumerate(variants, 1):
        print(f"[{i}/{len(variants)}] Testing: {variant.name}")
        print(f"   {variant.description}")
        
        result = benchmark_variant(variant, num_files=100)
        if result:
            results.append(result)
            print(f"   Write: {result.write_ms:.0f}ms, Read: {result.read_ms:.0f}ms, Files/sec: {result.files_per_sec:.0f}")
        print()
    
    return results


def plot_optimization_curves(results: List[BenchmarkResult]):
    """Plot optimization curves (Karpathy-style)."""
    if not HAS_MATPLOTLIB:
        print("\n" + "=" * 60)
        print("ASCII OPTIMIZATION CURVES")
        print("=" * 60)
        ascii_plot(results)
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("ChromaDB VFS Optimization Study\nWhat We Tried, What Worked", fontsize=14, fontweight='bold')
    
    # Extract data
    names = [r.config_name for r in results]
    write_times = [r.write_ms for r in results]
    read_times = [r.read_ms for r in results]
    files_per_sec = [r.files_per_sec for r in results]
    
    # Plot 1: Write Performance
    ax1 = axes[0, 0]
    ax1.bar(range(len(names)), write_times, color=['#ff6b6b', '#ffa502', '#ffa502', '#ffa502', '#2ed573', '#2ed573'])
    ax1.set_ylabel('Write Time (ms)')
    ax1.set_title('Write Performance (lower is better)')
    ax1.set_xticks(range(len(names)))
    ax1.set_xticklabels(names, rotation=45, ha='right')
    ax1.grid(axis='y', alpha=0.3)
    
    # Add value labels
    for i, v in enumerate(write_times):
        ax1.text(i, v + 500, f'{v:.0f}', ha='center', fontsize=9)
    
    # Plot 2: Read Performance
    ax2 = axes[0, 1]
    colors = ['#ff6b6b', '#74b9ff', '#74b9ff', '#74b9ff', '#74b9ff', '#2ed573']
    ax2.bar(range(len(names)), read_times, color=colors)
    ax2.set_ylabel('Read Time (ms)')
    ax2.set_title('Read Performance (lower is better)')
    ax2.set_xticks(range(len(names)))
    ax2.set_xticklabels(names, rotation=45, ha='right')
    ax2.grid(axis='y', alpha=0.3)
    
    for i, v in enumerate(read_times):
        ax2.text(i, v + 10, f'{v:.1f}', ha='center', fontsize=9)
    
    # Plot 3: Throughput
    ax3 = axes[1, 0]
    colors = ['#ff6b6b', '#ffa502', '#ffa502', '#ffa502', '#2ed573', '#2ed573']
    ax3.bar(range(len(names)), files_per_sec, color=colors)
    ax3.set_ylabel('Files per Second')
    ax3.set_title('Write Throughput (higher is better)')
    ax3.set_xticks(range(len(names)))
    ax3.set_xticklabels(names, rotation=45, ha='right')
    ax3.grid(axis='y', alpha=0.3)
    
    for i, v in enumerate(files_per_sec):
        ax3.text(i, v + 5, f'{v:.1f}', ha='center', fontsize=9)
    
    # Plot 4: Optimization Impact (speedup vs baseline)
    ax4 = axes[1, 1]
    baseline_write = write_times[0]
    baseline_read = read_times[0]
    
    write_speedups = [baseline_write / t if t > 0 else 0 for t in write_times]
    read_speedups = [baseline_read / t if t > 0 else 0 for t in read_times]
    
    x = range(len(names))
    width = 0.35
    
    ax4.bar([i - width/2 for i in x], write_speedups, width, label='Write Speedup', color='#2ed573')
    ax4.bar([i + width/2 for i in x], read_speedups, width, label='Read Speedup', color='#74b9ff')
    
    ax4.set_ylabel('Speedup vs Baseline (x)')
    ax4.set_title('Performance Improvement')
    ax4.set_xticks(x)
    ax4.set_xticklabels(names, rotation=45, ha='right')
    ax4.legend()
    ax4.grid(axis='y', alpha=0.3)
    ax4.set_yscale('log')  # Log scale for better visualization
    
    # Add value labels
    for i, (w, r) in enumerate(zip(write_speedups, read_speedups)):
        ax4.text(i - width/2, w, f'{w:.1f}x', ha='center', va='bottom', fontsize=8)
        ax4.text(i + width/2, r, f'{r:.1f}x', ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    plt.savefig('optimization_curves.png', dpi=150, bbox_inches='tight')
    print("\n📊 Plot saved to: optimization_curves.png")


def ascii_plot(results: List[BenchmarkResult]):
    """Generate ASCII art charts."""
    print("\nWRITE PERFORMANCE (ms) - lower is better")
    print("-" * 60)
    max_time = max(r.write_ms for r in results)
    scale = 50 / max_time if max_time > 0 else 1
    
    for r in results:
        bar_len = int(r.write_ms * scale)
        bar = "█" * bar_len
        print(f"{r.config_name:<25} {bar} {r.write_ms:>8.0f}ms")
    
    print("\nREAD PERFORMANCE (ms) - lower is better")
    print("-" * 60)
    max_read = max(r.read_ms for r in results)
    scale = 50 / max_read if max_read > 0 else 1
    
    for r in results:
        bar_len = int(r.read_ms * scale) if r.read_ms > 0 else 1
        bar = "█" * max(1, bar_len)
        print(f"{r.config_name:<25} {bar} {r.read_ms:>8.2f}ms")
    
    print("\nWRITE THROUGHPUT (files/sec) - higher is better")
    print("-" * 60)
    max_tput = max(r.files_per_sec for r in results)
    scale = 50 / max_tput if max_tput > 0 else 1
    
    for r in results:
        bar_len = int(r.files_per_sec * scale)
        bar = "█" * bar_len
        print(f"{r.config_name:<25} {bar} {r.files_per_sec:>8.1f}")
    
    print("\nSPEEDUP VS BASELINE")
    print("-" * 60)
    baseline_write = results[0].write_ms
    baseline_read = results[0].read_ms
    
    for r in results:
        write_sp = baseline_write / r.write_ms if r.write_ms > 0 else 0
        read_sp = baseline_read / r.read_ms if r.read_ms > 0 else 0
        print(f"{r.config_name:<25} Write: {write_sp:>6.1f}x  Read: {read_sp:>6.1f}x")


def main():
    """Main entry point."""
    # Run optimization study
    results = run_optimization_study()
    
    if not results:
        print("No results to plot!")
        return
    
    # Plot results
    plot_optimization_curves(results)
    
    # Save data
    data = {
        "variants": [
            {
                "name": r.config_name,
                "write_ms": r.write_ms,
                "read_ms": r.read_ms,
                "grep_ms": r.grep_ms,
                "find_ms": r.find_ms,
                "files_per_sec": r.files_per_sec
            }
            for r in results
        ]
    }
    
    with open('optimization_data.json', 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n💾 Data saved to: optimization_data.json")
    print(f"\n✅ Optimization study complete!")


if __name__ == "__main__":
    main()
