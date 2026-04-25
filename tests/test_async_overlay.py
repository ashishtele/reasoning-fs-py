"""Tests for AsyncOverlayFs async copy-on-write layer."""

import pytest
import asyncio
import tempfile
import shutil
from reasoning_fs.async_overlay import AsyncOverlayFs


@pytest.fixture
def temp_db():
    """Create temp directory for test DB."""
    temp = tempfile.mkdtemp()
    yield temp
    shutil.rmtree(temp, ignore_errors=True)


class TestAsyncOverlayFs:
    """Test AsyncOverlayFs functionality."""

    @pytest.mark.asyncio
    async def test_async_write_memory(self, temp_db):
        """Async write should be instant (memory only)."""
        vfs = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        
        start = asyncio.get_event_loop().time()
        await vfs.write("test/file.txt=content")
        elapsed = (asyncio.get_event_loop().time() - start) * 1000
        
        assert elapsed < 1.0  # Should be sub-millisecond
        content = await vfs.read("test/file.txt")
        assert content == "content"

    @pytest.mark.asyncio
    async def test_async_read_from_memory(self, temp_db):
        """Async read should return from memory buffer."""
        vfs = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        await vfs.write("src/main.py=def foo(): pass")
        
        content = await vfs.read("src/main.py")
        assert content == "def foo(): pass"

    @pytest.mark.asyncio
    async def test_async_delete_buffer(self, temp_db):
        """Delete should mark for deletion on sync."""
        vfs = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        await vfs.write("test/file.txt=to delete")
        
        # Should be readable before sync
        content = await vfs.read("test/file.txt")
        assert content == "to delete"
        
        await vfs.delete("test/file.txt")
        
        # Should raise after delete (before sync)
        with pytest.raises(FileNotFoundError):
            await vfs.read("test/file.txt")

    @pytest.mark.asyncio
    async def test_async_ls(self, temp_db):
        """ls should list files from memory."""
        vfs = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        await vfs.write("src/main.py=content1")
        await vfs.write("src/utils.py=content2")
        await vfs.write("test/test_main.py=content3")
        
        result = await vfs.ls("src/")
        assert "main.py" in result
        assert "utils.py" in result

    @pytest.mark.asyncio
    async def test_async_grep(self, temp_db):
        """grep should search content."""
        vfs = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        await vfs.write("src/main.py=def foo():\n    return 42")
        await vfs.write("src/utils.py=def bar():\n    return 100")
        
        result = await vfs.grep("foo")
        assert "main.py" in result
        assert "foo" in result

    @pytest.mark.asyncio
    async def test_async_find(self, temp_db):
        """find should match patterns."""
        vfs = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        await vfs.write("src/main.py=content")
        await vfs.write("src/utils.py=content")
        await vfs.write("test/test_main.py=content")
        
        result = await vfs.find("*.py")
        assert "src/main.py" in result
        assert "src/utils.py" in result

    @pytest.mark.asyncio
    async def test_async_sync(self, temp_db):
        """sync should flush to ChromaDB."""
        vfs = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        await vfs.write("test/file.txt=content")
        
        # Should be in memory
        content = await vfs.read("test/file.txt")
        assert content == "content"
        
        # Sync
        await vfs.sync()
        
        # Should still be readable (from cache)
        content = await vfs.read("test/file.txt")
        assert content == "content"

    @pytest.mark.asyncio
    async def test_async_auto_sync(self, temp_db):
        """auto_sync should trigger at batch_size."""
        vfs = AsyncOverlayFs(db_path=temp_db, batch_size=10, auto_sync=True)
        
        for i in range(10):
            await vfs.write(f"test/file_{i}.txt=content")
        
        # Should have synced
        stats = await vfs.stats()
        assert stats["write_buffer_size"] == 0

    @pytest.mark.asyncio
    async def test_async_stats(self, temp_db):
        """stats should return filesystem statistics."""
        vfs = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        await vfs.write("test/file1.txt=content1")
        await vfs.write("test/file2.txt=content2")
        
        stats = await vfs.stats()
        assert stats["total_files"] == 2
        assert stats["write_buffer_size"] == 2
        assert stats["db_path"] == temp_db

    @pytest.mark.asyncio
    async def test_async_concurrent_writes(self, temp_db):
        """Concurrent writes should not deadlock."""
        vfs = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        
        async def write_file(i):
            await vfs.write(f"test/file_{i}.txt=content_{i}")
        
        # Concurrent writes
        await asyncio.gather(*[write_file(i) for i in range(50)])
        
        # All should be readable
        for i in range(50):
            content = await vfs.read(f"test/file_{i}.txt")
            assert content == f"content_{i}"

    @pytest.mark.asyncio
    async def test_async_clear(self, temp_db):
        """clear should remove all data."""
        vfs = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        await vfs.write("test/file.txt=content")
        
        await vfs.clear()
        
        with pytest.raises(FileNotFoundError):
            await vfs.read("test/file.txt")

    @pytest.mark.asyncio
    async def test_async_persistence(self, temp_db):
        """Data should persist across instances."""
        # Write and sync
        vfs1 = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        await vfs1.write("test/file.txt=content")
        await vfs1.sync()
        
        # Create new instance
        vfs2 = AsyncOverlayFs(db_path=temp_db, auto_sync=False)
        
        # Should be readable from ChromaDB
        content = await vfs2.read("test/file.txt")
        assert content == "content"


# Run with: pytest tests/test_async_overlay.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])