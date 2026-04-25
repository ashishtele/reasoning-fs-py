# lmdb-vfs: Lightning-Fast Virtual Filesystem

[![PyPI](https://img.shields.io/pypi/v/lmdb-vfs.svg)](https://pypi.org/project/lmdb-vfs/)
[![Python](https://img.shields.io/pypi/pyversions/lmdb-vfs.svg)](https://pypi.org/project/lmdb-vfs/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A high-performance virtual filesystem backed by LMDB. **1200x faster** than ChromaDB for file storage operations.

## Why LMDB VFS?

Traditional filesystems are slow for programmatic access. ChromaDB is overkill (and 1200x slower). LMDB VFS gives you:

- ⚡ **1200x faster** than ChromaDB
- 💾 **90% less disk space** overhead
- 🔍 **Full-text search** (grep, find)
- 📁 **Directory support** (nested paths)
- 🔄 **ACID transactions**
- 🚀 **Memory-mapped I/O** (OS-level caching)

## Quick Start

```python
from lmdb_vfs import VFS

# Create/open database
vfs = VFS("mydb.lmdb")

# Write files
vfs.write("docs/report.txt", "Hello, World!")
vfs.write("src/main.py", "print('hello')")

# Read files
content = vfs.read("docs/report.txt")
print(content)  # "Hello, World!"

# Search
results = vfs.grep("hello")  # Find all files containing "hello"
files = vfs.find("*.py")     # Find all Python files

# List directories
items = vfs.listdir("docs")

# Close (or use context manager)
vfs.close()

# Better: use context manager
with VFS("mydb.lmdb") as vfs:
    vfs.write("test.txt", "content")
    print(vfs.read("test.txt"))
```

## Performance

**100 files, 1KB each:**

| Operation | ChromaDB | LMDB VFS | Speedup |
|-----------|----------|----------|---------|
| Write     | 12,938ms | 10.8ms   | **1,200x** |
| Read (300) | 313ms   | 0.26ms   | **1,200x** |
| Disk Size | 1,132KB  | 40KB     | **28x smaller** |

## Features

### File Operations

```python
vfs.write(path, content, metadata=None)  # Write file
vfs.read(path)                            # Read file
vfs.delete(path)                          # Delete file
vfs.exists(path)                          # Check existence
```

### Directory Operations

```python
vfs.mkdir(path)                           # Create directory
vfs.listdir(path)                         # List directory
vfs.walk(path)                            # Traverse tree
```

### Search Operations

```python
vfs.grep(pattern, path=None)              # Search content (regex)
vfs.find(pattern, path=None)              # Find files (glob)
```

### Advanced

```python
# Metadata support
vfs.write("file.txt", "content", {"author": "Alice", "version": "1.0"})

# Large databases
vfs = VFS("large.lmdb", map_size=10*1024**3)  # 10GB max

# Transactional operations
with vfs._env.begin(write=True) as txn:
    # Multiple operations in one transaction
    pass
```

## Installation

```bash
pip install lmdb-vfs
```

From source:

```bash
git clone https://github.com/ashishtele/reasoning-fs.git
cd reasoning-fs
pip install -e .
```

## API Reference

### VFS Class

```python
class VFS:
    """Lightweight virtual filesystem backed by LMDB."""
    
    def __init__(self, path: str, map_size: int = 1024**3)
    """Initialize VFS with LMDB backend.
    
    Args:
        path: Path to the LMDB database file.
        map_size: Maximum database size in bytes (default: 1GB).
    """
    
    def write(self, path: str, content: str, metadata: dict = None) -> None
    """Write content to a file."""
    
    def read(self, path: str) -> str
    """Read content from a file."""
    
    def delete(self, path: str) -> None
    """Delete a file."""
    
    def exists(self, path: str) -> bool
    """Check if file/directory exists."""
    
    def mkdir(self, path: str) -> None
    """Create a directory."""
    
    def listdir(self, path: str) -> List[str]
    """List directory contents."""
    
    def grep(self, pattern: str, path: str = None) -> List[Tuple[str, int, str]]
    """Search for pattern in file contents.
    
    Returns: List of (path, line_number, line) tuples.
    """
    
    def find(self, pattern: str, path: str = None) -> List[str]
    """Find files matching pattern.
    
    Args:
        pattern: Glob pattern (e.g., "*.txt").
        path: Optional path to search within.
    """
    
    def walk(self, path: str = ".") -> Iterator[Tuple[str, List[str], List[str]]]
    """Walk directory tree.
    
    Yields: (dirpath, dirnames, filenames) tuples.
    """
    
    def close(self) -> None
    """Close the database."""
```

## Use Cases

### 1. Agent Memory

```python
# Store conversation history
vfs.write("conversations/user123/session1.json", json.dumps(conversation))

# Search past conversations
results = vfs.grep("what is the capital of France?")
```

### 2. Document Search

```python
# Index documents
for doc in documents:
    vfs.write(f"docs/{doc.id}.txt", doc.content, {"tags": doc.tags})

# Full-text search
results = vfs.grep("machine learning")

# Filter by tags
python_files = vfs.find("*.py")
```

### 3. Version Control

```python
# Store file versions
vfs.write("project/main.py:v1", old_content)
vfs.write("project/main.py:v2", new_content)

# Compare versions
v1 = vfs.read("project/main.py:v1")
v2 = vfs.read("project/main.py:v2")
```

## Migration from ChromaDB

See [MIGRATION.md](MIGRATION.md) for detailed migration guide.

```python
# Old (ChromaDB)
from chromadb import PersistentClient
client = PersistentClient("db")
collection = client.get_collection("files")
collection.add(ids=[...], documents=[...], metadatas=[...])

# New (LMDB VFS)
from lmdb_vfs import VFS
vfs = VFS("db.lmdb")
vfs.write("path/to/file", content)
```

## Testing

```bash
# Run all tests
pytest tests/

# Run VFS tests only
pytest tests/test_vfs.py -v

# Run with coverage
pytest tests/ --cov=lmdb_vfs --cov-report=html
```

## Benchmark

```bash
# Run performance benchmarks
python benchmark_optimization.py
python redb_benchmark.py
python lmdb_benchmark.py

# Generate optimization curves
python optimization_curves.py
```

## License

MIT License. See [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/`
5. Submit a pull request

## Acknowledgments

- [LMDB](https://www.symas.com/symas-lmdb): Lightning Memory-Mapped Database
- [Karpathy's optimization curves](https://github.com/karpathy/autoresearch): Inspiration for benchmarking

---

**Built with ❤️ by Ashish Tele**
