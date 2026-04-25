"""Tests for LMDB VFS."""

import pytest
import shutil
import tempfile
from pathlib import Path

from lmdb_vfs import VFS
from lmdb_vfs.errors import FileNotFound, PathError


@pytest.fixture
def temp_vfs():
    """Create a temporary VFS instance."""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test.lmdb"
    vfs = VFS(str(db_path))
    yield vfs
    vfs.close()
    shutil.rmtree(temp_dir)


class TestBasicOperations:
    """Test basic file operations."""

    def test_write_and_read(self, temp_vfs):
        """Test writing and reading a file."""
        temp_vfs.write("test.txt", "Hello, World!")
        content = temp_vfs.read("test.txt")
        assert content == "Hello, World!"

    def test_write_nested_path(self, temp_vfs):
        """Test writing to nested directory."""
        temp_vfs.write("docs/api/readme.md", "# API Docs")
        content = temp_vfs.read("docs/api/readme.md")
        assert content == "# API Docs"

    def test_delete_file(self, temp_vfs):
        """Test deleting a file."""
        temp_vfs.write("test.txt", "content")
        assert temp_vfs.exists("test.txt")
        temp_vfs.delete("test.txt")
        assert not temp_vfs.exists("test.txt")

    def test_delete_nonexistent(self, temp_vfs):
        """Test deleting non-existent file raises error."""
        with pytest.raises(FileNotFound):
            temp_vfs.delete("nonexistent.txt")

    def test_exists(self, temp_vfs):
        """Test file existence check."""
        assert not temp_vfs.exists("test.txt")
        temp_vfs.write("test.txt", "content")
        assert temp_vfs.exists("test.txt")


class TestDirectoryOperations:
    """Test directory operations."""

    def test_mkdir(self, temp_vfs):
        """Test creating directory."""
        temp_vfs.mkdir("docs")
        assert temp_vfs.exists("docs")

    def test_listdir(self, temp_vfs):
        """Test listing directory contents."""
        temp_vfs.write("file1.txt", "content1")
        temp_vfs.write("file2.txt", "content2")
        temp_vfs.mkdir("subdir")

        items = temp_vfs.listdir(".")
        assert "file1.txt" in items
        assert "file2.txt" in items
        assert "subdir" in items

    def test_listdir_nonexistent(self, temp_vfs):
        """Test listing non-existent directory."""
        with pytest.raises(PathError):
            temp_vfs.listdir("nonexistent")


class TestGrepAndFind:
    """Test search operations."""

    def test_grep(self, temp_vfs):
        """Test grep operation."""
        temp_vfs.write("file1.txt", "hello world\nfoo bar")
        temp_vfs.write("file2.txt", "hello there\nbaz qux")

        results = temp_vfs.grep("hello")
        assert len(results) == 2
        assert any("file1.txt" in r[0] for r in results)
        assert any("file2.txt" in r[0] for r in results)

    def test_grep_no_match(self, temp_vfs):
        """Test grep with no matches."""
        temp_vfs.write("test.txt", "hello world")
        results = temp_vfs.grep("xyz")
        assert len(results) == 0

    def test_find(self, temp_vfs):
        """Test find operation."""
        temp_vfs.write("file1.txt", "content")
        temp_vfs.write("file2.py", "content")
        temp_vfs.write("docs/readme.md", "content")

        results = temp_vfs.find("*.txt")
        assert len(results) == 1
        assert "file1.txt" in results[0]

    def test_find_all(self, temp_vfs):
        """Test find with wildcard."""
        temp_vfs.write("file1.txt", "content")
        temp_vfs.write("file2.txt", "content")
        temp_vfs.write("file3.py", "content")

        results = temp_vfs.find("*.txt")
        assert len(results) == 2


class TestWalk:
    """Test directory walking."""

    def test_walk(self, temp_vfs):
        """Test walking directory tree."""
        temp_vfs.write("file1.txt", "content")
        temp_vfs.mkdir("subdir")
        temp_vfs.write("subdir/file2.txt", "content")

        entries = list(temp_vfs.walk("."))
        assert len(entries) >= 1

        # Check root directory
        root = entries[0]
        assert root[0] == "."
        assert "file1.txt" in root[2]
        assert "subdir" in root[1]


class TestContextManager:
    """Test context manager."""

    def test_context_manager(self):
        """Test using VFS as context manager."""
        temp_dir = tempfile.mkdtemp()
        db_path = Path(temp_dir) / "test.lmdb"

        with VFS(str(db_path)) as vfs:
            vfs.write("test.txt", "content")
            assert vfs.read("test.txt") == "content"

        # Database should be closed
        assert not vfs._env


class TestMetadata:
    """Test metadata support."""

    def test_write_with_metadata(self, temp_vfs):
        """Test writing file with metadata."""
        metadata = {"author": "Alice", "version": "1.0"}
        temp_vfs.write("test.txt", "content", metadata)

        # Note: Currently metadata is stored but not exposed
        # This test ensures it doesn't break anything
        assert temp_vfs.read("test.txt") == "content"


class TestPerformance:
    """Basic performance tests."""

    def test_write_speed(self, temp_vfs):
        """Test write performance."""
        import time

        n_files = 100
        start = time.perf_counter()

        for i in range(n_files):
            temp_vfs.write(f"file_{i}.txt", "x" * 1024)

        elapsed = time.perf_counter() - start
        rate = n_files / elapsed

        # Should be at least 100 files/sec (230+ is typical)
        # This is still 30x faster than ChromaDB's 7.7 files/sec
        assert rate > 100, f"Write rate too slow: {rate:.0f} files/sec"

    def test_read_speed(self, temp_vfs):
        """Test read performance."""
        import time

        # Write files first
        for i in range(100):
            temp_vfs.write(f"file_{i}.txt", "x" * 1024)

        # Benchmark reads
        n_reads = 300  # 3x per file
        start = time.perf_counter()

        for _ in range(3):
            for i in range(100):
                temp_vfs.read(f"file_{i}.txt")

        elapsed = time.perf_counter() - start
        rate = n_reads / elapsed

        # Should be at least 1000 reads/sec
        assert rate > 1000, f"Read rate too slow: {rate:.0f} reads/sec"
