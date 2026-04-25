#!/usr/bin/env python3
"""OverlayFs - Copy-on-Write layer for ChromaFs.

Provides:
- Instant writes to memory buffer
- Batched sync to ChromaDB
- Read-through from memory first
"""

import os
import time
from pathlib import Path
from typing import Dict, Set, Optional, Tuple, List, Any
from fnmatch import fnmatch


class OverlayFs:
    """Copy-on-Write filesystem layer over ChromaDB.
    
    Writes go to memory first (O(1)), then batch-sync to ChromaDB.
    Reads check memory first, then fall back to ChromaDB.
    
    Example:
        vfs = OverlayFs(db_path="./chroma_db", batch_size=50)
        vfs.write("file.txt=hello")  # Instant (memory)
        vfs.sync()  # Flush to ChromaDB
    """
    
    def __init__(
        self,
        db_path: str,
        batch_size: int = 50,
        auto_sync: bool = True,
    ):
        """Initialize OverlayFs.
        
        Args:
            db_path: Path to ChromaDB database
            batch_size: Number of writes before auto-sync
            auto_sync: If True, auto-sync when buffer reaches batch_size
        """
        self.db_path = db_path
        self.batch_size = batch_size
        self.auto_sync = auto_sync
        
        # In-memory write buffer
        self._write_buffer: Dict[str, str] = {}  # path -> content
        self._delete_buffer: Set[str] = set()  # paths marked for deletion
        
        # In-memory cache for reads
        self._read_cache: Dict[str, str] = {}  # path -> content
        
        # Path tree (in-memory, same as ChromaFs)
        self._path_set: Set[str] = set()
        self._dir_map: Dict[str, List[str]] = {}
        
        # Load existing state from ChromaDB
        self._load_state()
        
        # Sync counter
        self._write_count = 0
    
    def _load_state(self):
        """Load existing filesystem state from ChromaDB."""
        try:
            from chromadb import PersistentClient
            client = PersistentClient(path=self.db_path)
            collection = client.get_or_create_collection(name="filesystem")
            
            # Load all files into cache
            all_files = collection.get(include=["documents", "metadatas"])
            for meta, content in zip(all_files["metadatas"], all_files["documents"]):
                file_path = meta.get("path", "")
                if file_path and file_path != "__path_tree__":
                    self._read_cache[file_path] = content
                    self._path_set.add(file_path)
                    
                    # Update dir map
                    parts = file_path.rsplit("/", 1)
                    if len(parts) == 2:
                        dir_path, file_name = parts
                        if dir_path not in self._dir_map:
                            self._dir_map[dir_path] = []
                        if file_name not in self._dir_map[dir_path]:
                            self._dir_map[dir_path].append(file_name)
        except Exception:
            # No existing DB, start fresh
            pass
    
    def _flush_buffer(self):
        """Flush write buffer to ChromaDB in batch."""
        if not self._write_buffer and not self._delete_buffer:
            return
        
        from chromadb import PersistentClient
        client = PersistentClient(path=self.db_path)
        collection = client.get_or_create_collection(name="filesystem")
        
        # Process deletes
        for path in self._delete_buffer:
            try:
                existing = collection.get(where={"path": path})
                if existing["ids"]:
                    collection.delete(ids=existing["ids"])
            except Exception:
                pass
            
            # Update in-memory state
            self._read_cache.pop(path, None)
            self._path_set.discard(path)
            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                dir_path, file_name = parts
                if dir_path in self._dir_map and file_name in self._dir_map[dir_path]:
                    self._dir_map[dir_path].remove(file_name)
        
        # Process writes in batch
        if self._write_buffer:
            paths = list(self._write_buffer.keys())
            contents = [self._write_buffer[p] for p in paths]
            metadatas = [{"path": p} for p in paths]
            
            # Delete existing entries first (batch)
            for path in paths:
                try:
                    existing = collection.get(where={"path": path})
                    if existing["ids"]:
                        collection.delete(ids=existing["ids"])
                except Exception:
                    pass
            
            # Batch add
            try:
                collection.add(
                    documents=contents,
                    metadatas=metadatas,
                    ids=paths,
                )
            except Exception as e:
                # Fallback: add one by one
                for path, content, meta in zip(paths, contents, metadatas):
                    try:
                        collection.add(
                            documents=[content],
                            metadatas=[meta],
                            ids=[path],
                        )
                    except Exception:
                        pass
            
            # Update in-memory state
            for path in paths:
                self._read_cache[path] = self._write_buffer[path]
                self._path_set.add(path)
                
                parts = path.rsplit("/", 1)
                if len(parts) == 2:
                    dir_path, file_name = parts
                    if dir_path not in self._dir_map:
                        self._dir_map[dir_path] = []
                    if file_name not in self._dir_map[dir_path]:
                        self._dir_map[dir_path].append(file_name)
        
        # Clear buffers
        self._write_buffer.clear()
        self._delete_buffer.clear()
        self._write_count = 0
    
    def write(self, command: str) -> str:
        """Write a file to the virtual filesystem (instant, memory-only).
        
        Args:
            command: Command in format "path/to/file=content"
            
        Returns:
            Success message
        """
        if "=" not in command:
            raise ValueError("Invalid write command. Format: path/to/file=content")
        
        path, content = command.split("=", 1)
        path = path.strip()
        
        # Write to buffer (instant)
        self._write_buffer[path] = content
        self._write_count += 1
        
        # Update in-memory state immediately
        self._path_set.add(path)
        parts = path.rsplit("/", 1)
        if len(parts) == 2:
            dir_path, file_name = parts
            if dir_path not in self._dir_map:
                self._dir_map[dir_path] = []
            if file_name not in self._dir_map[dir_path]:
                self._dir_map[dir_path].append(file_name)
        
        # Auto-sync if buffer full
        if self.auto_sync and self._write_count >= self.batch_size:
            self.sync()
        
        return f"Written {path}"
    
    def read(self, path: str) -> str:
        """Read file content.
        
        Checks write buffer first, then read cache, then ChromaDB.
        
        Args:
            path: File path
            
        Returns:
            File content
        """
        # Check write buffer first
        if path in self._write_buffer:
            return self._write_buffer[path]
        
        # Check read cache
        if path in self._read_cache:
            return self._read_cache[path]
        
        # Fall back to ChromaDB
        try:
            from chromadb import PersistentClient
            client = PersistentClient(path=self.db_path)
            collection = client.get_or_create_collection(name="filesystem")
            
            results = collection.get(
                where={"path": path},
                include=["documents"],
            )
            
            if results["documents"]:
                content = results["documents"][0]
                self._read_cache[path] = content
                return content
        except Exception:
            pass
        
        raise FileNotFoundError(f"cat: {path}: No such file or directory")
    
    def cat(self, path: str) -> str:
        """Alias for read()."""
        return self.read(path)
    
    def ls(self, path: str = "") -> str:
        """List directory contents."""
        if not path:
            path = "."
        
        if path == ".":
            # Root level
            items = list(self._path_set)
        else:
            # Specific directory
            items = []
            for p in self._path_set:
                if p.startswith(path + "/"):
                    remainder = p[len(path) + 1:]
                    if "/" in remainder:
                        dir_name = remainder.split("/")[0]
                        if dir_name not in items:
                            items.append(dir_name)
                    else:
                        items.append(remainder)
        
        if not items:
            return ""
        
        return "\n".join(sorted(items))
    
    def find(self, pattern: str = "") -> str:
        """Find files by pattern."""
        results = []
        for path in self._path_set:
            if not pattern:
                results.append(path)
            elif pattern in path or fnmatch(Path(path).name, pattern):
                results.append(path)
        
        return "\n".join(sorted(results))
    
    def grep(self, command: str) -> str:
        """Grep for pattern in files.
        
        Args:
            command: "pattern" or "pattern file_path"
        """
        parts = command.split(maxsplit=1)
        pattern = parts[0]
        file_path = parts[1] if len(parts) > 1 else None
        
        results = []
        files = [file_path] if file_path else list(self._path_set)
        
        for path in files:
            try:
                content = self.read(path)
                for line_num, line in enumerate(content.split("\n"), 1):
                    if pattern in line:
                        results.append(f"{path}:{line_num}:{line}")
            except FileNotFoundError:
                continue
        
        return "\n".join(results)
    
    def delete(self, path: str) -> str:
        """Mark file for deletion (deletes on sync)."""
        self._delete_buffer.add(path)
        self._write_buffer.pop(path, None)  # Remove from write buffer if pending
        return f"Deleted {path}"
    
    def sync(self):
        """Flush write buffer to ChromaDB."""
        self._flush_buffer()
    
    def stats(self) -> Dict[str, Any]:
        """Get filesystem statistics."""
        return {
            "total_files": len(self._path_set),
            "write_buffer_size": len(self._write_buffer),
            "delete_buffer_size": len(self._delete_buffer),
            "read_cache_size": len(self._read_cache),
            "db_path": self.db_path,
        }
    
    def clear(self):
        """Clear all files."""
        self._write_buffer.clear()
        self._delete_buffer.clear()
        self._read_cache.clear()
        self._path_set.clear()
        self._dir_map.clear()
        
        # Also clear ChromaDB
        try:
            from chromadb import PersistentClient
            client = PersistentClient(path=self.db_path)
            collection = client.get_or_create_collection(name="filesystem")
            all_ids = collection.get()["ids"]
            if all_ids:
                collection.delete(ids=all_ids)
        except Exception:
            pass


if __name__ == "__main__":
    # Quick test
    import tempfile
    import shutil
    
    temp_db = tempfile.mkdtemp()
    vfs = OverlayFs(db_path=temp_db, batch_size=10)
    
    print("Writing 100 files...")
    start = time.time()
    for i in range(100):
        vfs.write(f"test/file_{i}.txt=content {i}")
    write_time = (time.time() - start) * 1000
    print(f"Write time: {write_time:.2f} ms ({write_time/100:.2f} ms/file)")
    
    print("\nReading 100 files...")
    start = time.time()
    for i in range(100):
        vfs.read(f"test/file_{i}.txt")
    read_time = (time.time() - start) * 1000
    print(f"Read time: {read_time:.2f} ms ({read_time/100:.2f} ms/file)")
    
    print("\nSyncing to ChromaDB...")
    start = time.time()
    vfs.sync()
    sync_time = (time.time() - start) * 1000
    print(f"Sync time: {sync_time:.2f} ms")
    
    print(f"\nStats: {vfs.stats()}")
    
    shutil.rmtree(temp_db)
