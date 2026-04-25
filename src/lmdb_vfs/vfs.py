"""LMDB-backed virtual filesystem implementation.

This module provides a high-performance virtual filesystem using LMDB
as the storage backend. It supports:
    - File read/write operations
    - Directory creation and listing
    - Grep and find operations
    - Path traversal
    - Transactional operations
"""

import os
import pickle
import re
import shutil
from pathlib import Path as Pathlib
from typing import Dict, List, Optional, Tuple, Iterator, Union
import lmdb

from .errors import FileNotFound, PathError, VFSError


class VFS:
    """Lightweight virtual filesystem backed by LMDB.

    A high-performance virtual filesystem that stores all files in a
    single LMDB database file. Provides filesystem-like operations with
    database performance.

    Attributes:
        path: Path to the LMDB database file.
        map_size: Maximum database size (default: 1GB).

    Example:
        >>> vfs = VFS("mydb.lmdb", map_size=1024**3)
        >>> vfs.write("docs/report.txt", "Hello, World!")
        >>> content = vfs.read("docs/report.txt")
        >>> print(content)
        Hello, World!
        >>> vfs.close()
    """

    def __init__(self, path: str, map_size: int = 1024**3):
        """Initialize VFS with LMDB backend.

        Args:
            path: Path to the LMDB database file.
            map_size: Maximum database size in bytes (default: 1GB).

        Raises:
            VFSError: If database cannot be opened.
        """
        self.path = path
        self.map_size = map_size
        self._env: Optional[lmdb.Environment] = None
        self._open()

    def _open(self) -> None:
        """Open the LMDB database."""
        # Create directory if it doesn't exist
        db_path = Pathlib(self.path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._env = lmdb.open(
                str(db_path),
                map_size=self.map_size,
                subdir=False,  # Single file
                readonly=False,
                lock=False,  # We handle our own locking
                readahead=False,
                meminit=False,
            )
        except Exception as e:
            raise VFSError(f"Failed to open LMDB database: {e}")

    def write(self, path: str, content: str, metadata: Optional[Dict] = None) -> None:
        """Write content to a file in the virtual filesystem.

        Args:
            path: File path (e.g., "docs/report.txt").
            content: File content as string.
            metadata: Optional metadata dictionary.

        Example:
            >>> vfs.write("docs/report.txt", "Hello, World!")
            >>> vfs.write("docs/notes.txt", "Meeting notes", {"author": "Alice"})
        """
        if not self._env:
            raise VFSError("Database not open")

        # Normalize path
        path = self._normalize_path(path)

        # Create parent directories if needed
        parent = str(Pathlib(path).parent)
        if parent != "." and not self.exists(parent):
            self.mkdir(parent)

        # Store file content and metadata
        data = {
            "content": content,
            "metadata": metadata or {},
        }

        with self._env.begin(write=True) as txn:
            txn.put(path.encode(), pickle.dumps(data))

    def read(self, path: str) -> str:
        """Read content from a file.

        Args:
            path: File path.

        Returns:
            File content as string.

        Raises:
            FileNotFound: If file doesn't exist.
        """
        if not self._env:
            raise VFSError("Database not open")

        path = self._normalize_path(path)

        with self._env.begin() as txn:
            data = txn.get(path.encode())

        if data is None:
            raise FileNotFound(f"File not found: {path}")

        return pickle.loads(data)["content"]

    def delete(self, path: str) -> None:
        """Delete a file.

        Args:
            path: File path.

        Raises:
            FileNotFound: If file doesn't exist.
        """
        if not self._env:
            raise VFSError("Database not open")

        path = self._normalize_path(path)

        with self._env.begin(write=True) as txn:
            if not txn.delete(path.encode()):
                raise FileNotFound(f"File not found: {path}")

    def exists(self, path: str) -> bool:
        """Check if a file or directory exists.

        Args:
            path: File or directory path.

        Returns:
            True if exists, False otherwise.
        """
        if not self._env:
            raise VFSError("Database not open")

        path = self._normalize_path(path)

        with self._env.begin() as txn:
            data = txn.get(path.encode())
            if data is not None:
                return True

            # Check if it's a directory
            prefix = path + "/"
            cursor = txn.cursor()
            if cursor.set_range(prefix.encode()):
                key = cursor.key().decode()
                if key.startswith(prefix):
                    return True

        return False

    def mkdir(self, path: str) -> None:
        """Create a directory.

        Args:
            path: Directory path.
        """
        if not self._env:
            raise VFSError("Database not open")

        path = self._normalize_path(path)

        # Store directory marker
        with self._env.begin(write=True) as txn:
            txn.put(f"{path}/__dir__".encode(), pickle.dumps({}))

    def listdir(self, path: str) -> List[str]:
        """List contents of a directory.

        Args:
            path: Directory path.

        Returns:
            List of file/directory names.

        Raises:
            PathError: If path is not a directory.
        """
        if not self._env:
            raise VFSError("Database not open")

        path = self._normalize_path(path)

        # Check if directory exists (skip check for root ".")
        if path != "." and not self.exists(path):
            raise PathError(f"Directory not found: {path}")

        items = set()
        prefix = f"{path}/" if path != "." else ""

        with self._env.begin() as txn:
            cursor = txn.cursor()
            # Start from beginning or prefix
            if prefix:
                if not cursor.set_range(prefix.encode()):
                    return []
            else:
                if not cursor.first():
                    return []

            while True:
                try:
                    key = cursor.key().decode()
                except (StopIteration, TypeError):
                    break

                # Stop if we've gone past our prefix
                if prefix and not key.startswith(prefix):
                    break
                elif not prefix and key.startswith("__dir__"):
                    # Skip root-level directory markers
                    if not cursor.next():
                        break
                    continue

                # Extract immediate child
                relative = key[len(prefix):] if prefix else key
                if "/" in relative:
                    child = relative.split("/")[0]
                else:
                    # Skip directory markers
                    if relative == "__dir__":
                        if not cursor.next():
                            break
                        continue
                    child = relative

                items.add(child)
                if not cursor.next():
                    break

        return sorted(list(items))

    def grep(self, pattern: str, path: Optional[str] = None) -> List[Tuple[str, int, str]]:
        """Search for pattern in file contents.

        Args:
            pattern: Regex pattern to search for.
            path: Optional path to search within (default: all files).

        Returns:
            List of (path, line_number, line) tuples.
        """
        if not self._env:
            raise VFSError("Database not open")

        results = []
        regex = re.compile(pattern)

        with self._env.begin() as txn:
            cursor = txn.cursor()

            # Filter by path if specified
            prefix = f"{self._normalize_path(path)}/" if path else None

            for key, value in cursor:
                key_str = key.decode()

                # Skip directory markers
                if key_str.endswith("/__dir__"):
                    continue

                # Filter by path
                if prefix and not key_str.startswith(prefix):
                    continue

                try:
                    data = pickle.loads(value)
                    content = data.get("content", "")

                    for line_num, line in enumerate(content.split("\n"), 1):
                        if regex.search(line):
                            results.append((key_str, line_num, line))
                except Exception:
                    continue

        return results

    def find(self, pattern: str, path: Optional[str] = None) -> List[str]:
        """Find files matching pattern.

        Args:
            pattern: Glob pattern (e.g., "*.txt", "docs/*").
            path: Optional path to search within.

        Returns:
            List of matching file paths.
        """
        if not self._env:
            raise VFSError("Database not open")

        # Convert glob to regex
        regex_pattern = pattern.replace(".", r"\.").replace("*", ".*")
        regex = re.compile(f"^{regex_pattern}$")

        results = []
        prefix = f"{self._normalize_path(path)}/" if path else None

        with self._env.begin() as txn:
            cursor = txn.cursor()

            for key, _ in cursor:
                key_str = key.decode()

                # Skip directory markers
                if key_str.endswith("/__dir__"):
                    continue

                # Filter by path
                if prefix and not key_str.startswith(prefix):
                    continue

                # Check if filename matches pattern
                filename = key_str.split("/")[-1]
                if regex.search(filename) or regex.search(key_str):
                    results.append(key_str)

        return sorted(results)

    def walk(self, path: str = ".") -> Iterator[Tuple[str, List[str], List[str]]]:
        """Walk directory tree.

        Args:
            path: Starting path (default: root).

        Yields:
            (dirpath, dirnames, filenames) tuples.
        """
        if not self._env:
            raise VFSError("Database not open")

        path = self._normalize_path(path)
        prefix = f"{path}/" if path != "." else ""

        dirs = set()
        files = []

        with self._env.begin() as txn:
            cursor = txn.cursor()

            for key, _ in cursor:
                key_str = key.decode()

                # Skip directory markers
                if key_str.endswith("/__dir__"):
                    continue

                # Filter by path
                if prefix and not key_str.startswith(prefix):
                    continue

                relative = key_str[len(prefix):] if prefix else key_str
                parts = relative.split("/")

                if len(parts) == 1:
                    files.append(key_str)
                else:
                    dirs.add(parts[0])

        yield path, sorted(list(dirs)), sorted(files)

        # Recurse into subdirectories
        for dir_name in dirs:
            subpath = f"{path}/{dir_name}" if path != "." else dir_name
            yield from self.walk(subpath)

    def _normalize_path(self, path: str) -> str:
        """Normalize path string."""
        # Remove leading/trailing slashes
        path = path.strip("/")

        # Handle empty path
        if not path:
            return "."

        # Normalize double slashes
        while "//" in path:
            path = path.replace("//", "/")

        return path

    def close(self) -> None:
        """Close the database."""
        if self._env:
            self._env.close()
            self._env = None

    def __enter__(self) -> "VFS":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def __del__(self) -> None:
        """Destructor."""
        self.close()
