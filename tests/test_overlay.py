"""Tests for OverlayFs copy-on-write layer."""

import pytest
import tempfile
import shutil
from reasoning_fs.overlay import OverlayFs


class TestOverlayFs:
    """Test OverlayFs functionality."""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database path."""
        temp_db = tempfile.mkdtemp()
        yield temp_db
        shutil.rmtree(temp_db)
    
    def test_instant_write(self, temp_db):
        """Writes should be instant (memory-only)."""
        vfs = OverlayFs(db_path=temp_db, batch_size=1000, auto_sync=False)
        
        import time
        start = time.time()
        vfs.write("test/file.txt=content")
        write_time = (time.time() - start) * 1000
        
        # Should be sub-millisecond
        assert write_time < 1.0, f"Write took {write_time}ms, expected <1ms"
        assert vfs.read("test/file.txt") == "content"
    
    def test_read_from_buffer(self, temp_db):
        """Read should return buffered writes immediately."""
        vfs = OverlayFs(db_path=temp_db, auto_sync=False)
        vfs.write("test/file.txt=buffered content")
        
        # Read from buffer (not synced yet)
        assert vfs.read("test/file.txt") == "buffered content"
    
    def test_sync_persists(self, temp_db):
        """Sync should persist writes to ChromaDB."""
        vfs = OverlayFs(db_path=temp_db, auto_sync=False)
        vfs.write("test/file.txt=persisted content")
        
        # Sync
        vfs.sync()
        
        # Load fresh instance
        vfs2 = OverlayFs(db_path=temp_db, auto_sync=False)
        assert vfs2.read("test/file.txt") == "persisted content"
    
    def test_auto_sync(self, temp_db):
        """Auto-sync should trigger when buffer reaches batch_size."""
        vfs = OverlayFs(db_path=temp_db, batch_size=5, auto_sync=True)
        
        # Write 5 files (should trigger auto-sync on 5th)
        for i in range(5):
            vfs.write(f"test/file_{i}.txt=content {i}")
        
        # Buffer should be empty after auto-sync
        assert len(vfs._write_buffer) == 0
        
        # Should be persisted
        vfs2 = OverlayFs(db_path=temp_db, auto_sync=False)
        assert vfs2.read("test/file_4.txt") == "content 4"
    
    def test_delete_buffer(self, temp_db):
        """Delete should mark for deletion on sync."""
        vfs = OverlayFs(db_path=temp_db, auto_sync=False)
        vfs.write("test/file.txt=to delete")
        assert vfs.read("test/file.txt") == "to delete"
        
        # Mark for deletion
        vfs.delete("test/file.txt")
        
        # Should still be readable from read_cache (not synced yet)
        # Note: delete removes from write_buffer but file content is in read_cache
        # After sync, it will be truly deleted
        with pytest.raises(FileNotFoundError):
            vfs.read("test/file.txt")  # Not in write_buffer, not in read_cache
        
        # Sync
        vfs.sync()
        
        # Should still be deleted
        with pytest.raises(FileNotFoundError):
            vfs.read("test/file.txt")
    
    def test_ls(self, temp_db):
        """ls should list files."""
        vfs = OverlayFs(db_path=temp_db, auto_sync=False)
        vfs.write("src/main.py=code")
        vfs.write("src/utils.py=code")
        vfs.write("tests/test_main.py=tests")
        
        # List root
        assert "src" in vfs.ls()
        assert "tests" in vfs.ls()
        
        # List src
        files = vfs.ls("src").split("\n")
        assert "main.py" in files
        assert "utils.py" in files
    
    def test_find(self, temp_db):
        """find should match patterns."""
        vfs = OverlayFs(db_path=temp_db, auto_sync=False)
        vfs.write("src/main.py=code")
        vfs.write("src/utils.py=code")
        vfs.write("tests/test_main.py=tests")
        
        # Find all
        assert len(vfs.find().split("\n")) == 3
        
        # Find by pattern
        results = vfs.find("*.py").split("\n")
        assert len(results) == 3
        
        # Find by name
        results = vfs.find("main").split("\n")
        assert len(results) == 2  # src/main.py and tests/test_main.py
    
    def test_grep(self, temp_db):
        """grep should search content."""
        vfs = OverlayFs(db_path=temp_db, auto_sync=False)
        vfs.write("src/main.py=def foo():\n    return 42")
        vfs.write("src/utils.py=def bar():\n    return foo()")
        
        # Grep for 'foo' (pattern only, searches all files)
        results = vfs.grep("foo").split("\n")
        assert len(results) == 2
        
        # Grep for specific file
        results = vfs.grep("foo src/main.py").split("\n")
        assert len(results) == 1
        assert "src/main.py" in results[0]
    
    def test_stats(self, temp_db):
        """stats should return filesystem statistics."""
        vfs = OverlayFs(db_path=temp_db, auto_sync=False)
        vfs.write("test/file1.txt=content1")
        vfs.write("test/file2.txt=content2")
        
        stats = vfs.stats()
        assert stats["total_files"] == 2
        assert stats["write_buffer_size"] == 2
        # read_cache_size is 0 until read() from ChromaDB (after sync)
        assert stats["read_cache_size"] == 0
        
        # Sync to persist
        vfs.sync()
        
        # Read files to populate cache (from ChromaDB)
        vfs.read("test/file1.txt")
        vfs.read("test/file2.txt")
        
        stats = vfs.stats()
        assert stats["read_cache_size"] == 2
    
    def test_clear(self, temp_db):
        """clear should remove all files."""
        vfs = OverlayFs(db_path=temp_db, auto_sync=False)
        vfs.write("test/file1.txt=content1")
        vfs.write("test/file2.txt=content2")
        
        vfs.clear()
        
        assert len(vfs._path_set) == 0
        assert len(vfs._write_buffer) == 0
        assert len(vfs._read_cache) == 0
