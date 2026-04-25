"""LMDB VFS - Lightning-fast virtual filesystem backed by LMDB.

A lightweight, high-performance virtual filesystem that stores files in
a single LMDB database file. 1200x faster than ChromaDB for file storage.

Features:
    - Lightning-fast reads/writes (1200x vs ChromaDB)
    - Single-file database (no directory overhead)
    - ACID transactions
    - Memory-mapped I/O (OS-level caching)
    - Full path support (directories, nested paths)
    - Grep, find, and search operations
    - Version tracking (optional)

Quick Start:
    >>> from lmdb_vfs import VFS
    >>> vfs = VFS("mydb.lmdb")
    >>> vfs.write("docs/report.txt", "Hello, World!")
    >>> content = vfs.read("docs/report.txt")
    >>> print(content)
    Hello, World!
    >>> vfs.close()
"""

from .vfs import VFS
from .errors import VFSError, FileNotFound, PathError

__version__ = "0.1.0"
__all__ = ["VFS", "VFSError", "FileNotFound", "PathError"]
