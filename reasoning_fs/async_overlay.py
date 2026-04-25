#!/usr/bin/env python3
"""AsyncOverlayFs - Async copy-on-write layer for ChromaFs.

Provides:
- Async writes to memory buffer (instant)
- Batched async sync to ChromaDB
- Async read-through from memory first
"""

import os
import asyncio
import tempfile
import shutil
from typing import Dict, Set, Optional, List, Tuple
from dataclasses import dataclass, field
import hashlib
import time


@dataclass
class AsyncOverlayFs:
    """Async Copy-on-Write filesystem layer over ChromaDB.
    
    Usage:
        vfs = AsyncOverlayFs(db_path="/tmp/agent_workspace", batch_size=100)
        
        # Async writes (instant)
        await vfs.write("src/main.py=def foo(): pass")
        await vfs.write("src/utils.py=def bar(): pass")
        
        # Async reads (sub-ms)
        content = await vfs.read("src/main.py")
        
        # Batched sync
        await vfs.sync()
    """
    
    db_path: str
    batch_size: int = 100
    auto_sync: bool = True
    
    _collection: any = field(default=None, init=False)
    _write_buffer: Dict[str, str] = field(default_factory=dict, init=False)
    _read_cache: Dict[str, str] = field(default_factory=dict, init=False)
    _path_set: Set[str] = field(default_factory=set, init=False)
    _delete_buffer: Set[str] = field(default_factory=set, init=False)
    _write_count: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    
    def __post_init__(self):
        """Initialize ChromaDB collection (sync, but fast)."""
        import chromadb
        from chromadb.config import Settings
        
        os.makedirs(self.db_path, exist_ok=True)
        
        # Sync client for initialization (ChromaDB async is limited)
        client = chromadb.PersistentClient(path=self.db_path)
        self._collection = client.get_or_create_collection(
            name="path_tree",
            metadata={"description": "Virtual filesystem path tree"}
        )
        
        # Load existing paths into memory
        self._load_existing_paths()
    
    def _load_existing_paths(self):
        """Load existing paths from ChromaDB into memory."""
        try:
            all_files = self._collection.get(include=["metadatas"])
            for meta in all_files["metadatas"]:
                if meta:
                    self._path_set.add(meta.get("path", ""))
        except Exception:
            pass  # Empty DB is fine
    
    async def write(self, command: str) -> str:
        """Async write to memory buffer.
        
        Args:
            command: Command in format "path/to/file=content"
            
        Returns:
            Confirmation message
        """
        async with self._lock:
            if "=" not in command:
                raise ValueError("write requires format: path=content")
            
            path, content = command.split("=", 1)
            
            # Store in write buffer (instant)
            self._write_buffer[path] = content
            self._path_set.add(path)
            self._write_count += 1
            
            # Auto-sync if threshold reached
            if self.auto_sync and self._write_count >= self.batch_size:
                await self._flush_buffer()
            
            return f"Written {path} ({len(content)} bytes)"
    
    async def read(self, path: str) -> str:
        """Async read from memory or ChromaDB.
        
        Args:
            path: File path to read
            
        Returns:
            File content
        """
        async with self._lock:
            # Check write buffer first (most recent)
            if path in self._write_buffer:
                return self._write_buffer[path]
            
            # Check read cache
            if path in self._read_cache:
                return self._read_cache[path]
            
            # Check if path exists (in memory set)
            if path not in self._path_set:
                raise FileNotFoundError(f"File not found: {path}")
            
            # Fallback to ChromaDB (slow, but persistent)
            results = self._collection.get(
                where={"path": path},
                include=["documents"]
            )
            
            if results["documents"] and results["documents"][0]:
                content = results["documents"][0]
                self._read_cache[path] = content
                return content
            
            raise FileNotFoundError(f"File not found in DB: {path}")
    
    async def ls(self, path: str = "") -> str:
        """Async list directory contents.
        
        Uses in-memory cache for O(1) lookup.
        """
        # Auto-sync if dirty
        if self._write_buffer or self._delete_buffer:
            await self._flush_buffer()
        
        if not path:
            path = "."
        
        # Normalize path
        if path != ".":
            path = path.rstrip("/")
        
        # Filter paths from memory
        if path == ".":
            # Root level
            dirs = set()
            files = set()
            for p in self._path_set:
                if "/" in p:
                    dirs.add(p.split("/")[0])
                else:
                    files.add(p)
            result = sorted(dirs) + sorted(files)
        else:
            # Specific directory
            prefix = path + "/"
            entries = set()
            for p in self._path_set:
                if p.startswith(prefix):
                    remainder = p[len(prefix):]
                    if "/" in remainder:
                        entries.add(remainder.split("/")[0] + "/")
                    else:
                        entries.add(remainder)
            result = sorted(entries)
        
        return "\n".join(result) if result else "(empty)"
    
    async def cat(self, path: str) -> str:
        """Async read file content (alias for read)."""
        return await self.read(path)
    
    async def grep(self, command: str) -> str:
        """Async grep for pattern in files.
        
        Args:
            command: "pattern" or "pattern file_path"
        """
        parts = command.split(maxsplit=1)
        if len(parts) < 1:
            raise ValueError("grep requires pattern")
        
        pattern = parts[0]
        file_path = parts[1] if len(parts) > 1 else None
        
        matches = []
        
        # Search in write buffer and read cache
        for p, content in {**self._write_buffer, **self._read_cache}.items():
            if file_path and not p.startswith(file_path):
                continue
            if pattern in content:
                matches.append(f"{p}: {content[:100]}...")
        
        # Search in ChromaDB for uncached files
        if not matches:
            all_files = self._collection.get(include=["documents", "metadatas"])
            for doc, meta in zip(all_files["documents"], all_files["metadatas"]):
                if meta and file_path and not meta.get("path", "").startswith(file_path):
                    continue
                if pattern in doc:
                    matches.append(f"{meta.get('path', '')}: {doc[:100]}...")
        
        return "\n".join(matches) if matches else "(no matches)"
    
    async def find(self, pattern: str = "") -> str:
        """Async find files by name pattern.
        
        Uses in-memory cache for O(1) lookup.
        """
        # Auto-sync if dirty
        if self._write_buffer or self._delete_buffer:
            await self._flush_buffer()
        
        if not pattern:
            return "\n".join(sorted(self._path_set))
        
        # Simple glob matching
        import fnmatch
        matches = [p for p in self._path_set if fnmatch.fnmatch(p, pattern)]
        return "\n".join(sorted(matches)) if matches else "(no matches)"
    
    async def delete(self, path: str) -> str:
        """Mark file for deletion (removes on sync)."""
        async with self._lock:
            self._delete_buffer.add(path)
            self._write_buffer.pop(path, None)  # Remove from write buffer
            self._path_set.discard(path)
            
            return f"Deleted {path}"
    
    async def sync(self) -> str:
        """Explicit sync to ChromaDB."""
        async with self._lock:
            await self._flush_buffer()
            return "Sync complete"
    
    async def _flush_buffer(self):
        """Flush write buffer to ChromaDB (async)."""
        if not self._write_buffer and not self._delete_buffer:
            return
        
        # Batch ChromaDB operations (still sync, but batched)
        if self._write_buffer:
            # Prepare batch
            paths = list(self._write_buffer.keys())
            contents = [self._write_buffer[p] for p in paths]
            
            # Generate embeddings (fake for now - same as OverlayFs)
            embeddings = []
            for content in contents:
                import hashlib
                hash_int = int(hashlib.md5(content.encode()).hexdigest()[:8], 16)
                embeddings.append([float(hash_int) / 2**32] * 100)
            
            # Add to ChromaDB (batched)
            self._collection.add(
                ids=[f"path_{i}" for i in range(len(paths))],
                embeddings=embeddings,
                documents=contents,
                metadatas=[{"path": p} for p in paths]
            )
            
            # Clear write buffer
            self._write_buffer.clear()
            self._write_count = 0
        
        # Handle deletes
        if self._delete_buffer:
            for path in self._delete_buffer:
                try:
                    results = self._collection.get(
                        where={"path": path},
                        include=["ids"]
                    )
                    if results["ids"]:
                        self._collection.delete(ids=results["ids"])
                except Exception:
                    pass  # Path may not exist in DB yet
            
            self._delete_buffer.clear()
    
    async def clear(self):
        """Clear all data (memory and DB)."""
        async with self._lock:
            self._write_buffer.clear()
            self._read_cache.clear()
            self._path_set.clear()
            self._delete_buffer.clear()
            self._write_count = 0
            # Delete all from ChromaDB (no where clause)
            all_ids = self._collection.get()["ids"]
            if all_ids:
                self._collection.delete(ids=all_ids)
    
    async def stats(self) -> dict:
        """Get filesystem statistics."""
        async with self._lock:
            all_files = self._collection.get(include=["documents", "metadatas"])
            total_size = sum(len(doc) for doc in all_files["documents"])
            
            return {
                "total_files": len(self._path_set),
                "write_buffer_size": len(self._write_buffer),
                "read_cache_size": len(self._read_cache),
                "delete_buffer_size": len(self._delete_buffer),
                "total_size_bytes": total_size,
                "db_path": self.db_path
            }


# Quick benchmark
if __name__ == "__main__":
    import asyncio
    
    async def benchmark():
        temp_db = tempfile.mkdtemp()
        vfs = AsyncOverlayFs(db_path=temp_db, batch_size=100, auto_sync=False)
        
        # Write 100 files
        start = time.time()
        for i in range(100):
            await vfs.write(f"test/file_{i}.py=def function_{i}():\n    return {i}")
        write_time = (time.time() - start) * 1000
        
        # Read 100 files (from memory, before sync)
        start = time.time()
        for i in range(100):
            await vfs.read(f"test/file_{i}.py")
        read_time_memory = (time.time() - start) * 1000
        
        # Sync
        start = time.time()
        await vfs.sync()
        sync_time = (time.time() - start) * 1000
        
        # Read 100 files (from cache after sync)
        start = time.time()
        for i in range(100):
            await vfs.read(f"test/file_{i}.py")
        read_time_cached = (time.time() - start) * 1000
        
        print(f"\n{'='*60}")
        print("AsyncOverlayFs BENCHMARK")
        print(f"{'='*60}")
        print(f"Write 100 files: {write_time:.2f} ms ({write_time/100:.4f} ms/file)")
        print(f"Read 100 files (memory): {read_time_memory:.2f} ms ({read_time_memory/100:.4f} ms/file)")
        print(f"Sync to ChromaDB: {sync_time:.2f} ms ({sync_time/100:.2f} ms/file)")
        print(f"Read 100 files (cached): {read_time_cached:.2f} ms ({read_time_cached/100:.4f} ms/file)")
        print(f"{'='*60}\n")
        
        shutil.rmtree(temp_db)
    
    asyncio.run(benchmark())