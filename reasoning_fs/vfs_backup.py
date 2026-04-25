"""Virtual filesystem over ChromaDB.

Based on Mintlify's ChromaFs pattern:
- Store entire directory tree as __path_tree__ blob for O(1) navigation
- Dual in-memory cache: Set of paths + Map of dir→children
- UNIX-like commands (grep, cat, ls, find, write, read)
- No Docker/container dependencies - pure ChromaDB
"""

from typing import Any, Dict, List, Optional, Set, Tuple
import re
import uuid
import json
import gzip
import base64
import shlex
import chromadb


class ChromaFs:
    """Virtual filesystem over ChromaDB.
    
    Provides UNIX-like commands over a vector database:
    - `ls path/` - list files/directories
    - `cat file.txt` - read file contents
    - `grep pattern` - search for patterns
    - `find name` - find files by name
    - `write path=content` - write file
    - `read path` - read file (alias for cat)
    
    Key optimizations from Mintlify's implementation:
    - __path_tree__: Gzipped JSON blob storing entire file tree
    - In-memory Set<string> for O(1) path lookup
    - In-memory Map<string, string[]> for O(1) directory listing
    
    Example:
        >>> vfs = ChromaFs(db_path="vfs_db")
        >>> vfs.write("src/main.py=print('hello')")
        >>> print(vfs.cat("src/main.py"))
        >>> results = vfs.grep("hello")
    """

    def __init__(self, db_path: str = "vfs_db"):
        """Initialize VFS with ChromaDB and bootstrap path tree.
        
        Args:
            db_path: Path to ChromaDB persistence directory
        """
        self.db_path = db_path
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name="filesystem",
            metadata={"description": "Virtual filesystem"},
        )
        
        # In-memory caches (Mintlify pattern)
        self._path_set: Set[str] = set()
        self._dir_map: Dict[str, List[str]] = {}
        self._tree_saved: bool = False
        
        # Bootstrap from existing files (don't save empty tree yet)
        self._bootstrap_path_tree()

    def _bootstrap_path_tree(self):
        """Load path tree from __path_tree__ blob or scan existing files."""
        # Check for __path_tree__ blob
        existing = self.collection.get(
            where={"path": "__path_tree__"},
            include=["documents", "metadatas"],
        )
        
        if existing["ids"]:
            # Decompress and load tree (base64 decode first)
            compressed = base64.b64decode(existing["documents"][0])
            tree_data = json.loads(gzip.decompress(compressed).decode())
            self._path_set = set(tree_data.keys())
            self._tree_saved = True
            
            # Build directory map
            for path in self._path_set:
                parts = path.rsplit("/", 1)
                if len(parts) == 2:
                    dir_path, file_name = parts
                    if dir_path not in self._dir_map:
                        self._dir_map[dir_path] = []
                    self._dir_map[dir_path].append(file_name)
        else:
            # Scan existing files and build tree
            all_files = self.collection.get(include=["metadatas"])
            for meta, doc_id in zip(all_files["metadatas"], all_files["ids"]):
                path = meta.get("path")
                if path and path != "__path_tree__":
                    self._path_set.add(path)
                    parts = path.rsplit("/", 1)
                    if len(parts) == 2:
                        dir_path, file_name = parts
                        if dir_path not in self._dir_map:
                            self._dir_map[dir_path] = []
                        self._dir_map[dir_path].append(file_name)
            
            # Only save if we found files
            if self._path_set:
                self._save_path_tree()
                self._tree_saved = True

    def _save_path_tree(self):
        """Save path tree as gzipped JSON blob (base64 encoded)."""
        tree_data = {path: {} for path in self._path_set}
        compressed = gzip.compress(json.dumps(tree_data).encode())
        encoded = base64.b64encode(compressed).decode()
        
        # Delete old blob if exists
        existing = self.collection.get(
            where={"path": "__path_tree__"},
        )
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])
        
        # Save new blob
        self.collection.add(
            ids=[uuid.uuid4().hex],
            documents=[encoded],
            metadatas=[{"path": "__path_tree__"}],
        )

    def _parse_command(self, command: str) -> Tuple[str, str]:
        """Parse UNIX-like command into (cmd, arg).
        
        Uses shlex for proper argument parsing (like just-bash).
        """
        try:
            tokens = shlex.split(command)
            if not tokens:
                return "", ""
            cmd = tokens[0]
            arg = " ".join(tokens[1:]) if len(tokens) > 1 else ""
            return cmd, arg
        except ValueError:
            # Fallback to simple split
            parts = command.strip().split(None, 1)
            return (parts[0], parts[1]) if len(parts) > 1 else (parts[0], "")

    def ls(self, path: str = "") -> str:
        """List files/directories at path.
        
        Uses in-memory cache for O(1) lookup.
        """
        # Save tree if dirty (lazy save)
        if not self._tree_saved:
            self._save_path_tree()
            self._tree_saved = True
        
        if not path:
            path = "."
        
        # Normalize path
        if path == ".":
            # Root level
            children = []
            for dir_path in self._dir_map.keys():
                if "/" not in dir_path:
                    children.append(dir_path + "/")
                else:
                    parent = dir_path.split("/")[0]
                    if parent not in [c.rstrip("/") for c in children]:
                        children.append(parent + "/")
            children.extend([p for p in self._path_set if "/" not in p])
            return "\n".join(sorted(set(children)))
        
        # Remove trailing slash
        path = path.rstrip("/")
        
        # Check if path exists
        if path not in self._path_set:
            # Check if it's a directory
            if path in self._dir_map:
                children = [f"{name}" for name in self._dir_map[path]]
                dirs = [f"{name}/" for name in self._dir_map.get(path, [])]
                return "\n".join(sorted(dirs + children))
            return f"ls: cannot access '{path}': No such file or directory"
        
        # It's a file
        return path

    def cat(self, path: str) -> str:
        """Read file contents.
        
        Args:
            path: File path to read
            
        Returns:
            File contents
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        path = path.strip()
        
        if path not in self._path_set:
            raise FileNotFoundError(f"cat: {path}: No such file or directory")
        
        # Get file content from ChromaDB
        results = self.collection.get(
            where={"path": path},
            include=["documents"],
        )
        
        if not results["ids"]:
            raise FileNotFoundError(f"cat: {path}: File not found in database")
        
        return results["documents"][0]

    def grep(self, pattern: str) -> str:
        """Search for pattern in all files.
        
        Args:
            pattern: Regex pattern to search for
            
        Returns:
            Matching lines with file paths
        """
        pattern = pattern.strip()
        if not pattern:
            return "grep: No pattern specified"
        
        # Get all files
        all_files = self.collection.get(include=["documents", "metadatas"])
        
        matches = []
        for doc, meta in zip(all_files["documents"], all_files["metadatas"]):
            path = meta.get("path", "unknown")
            try:
                regex = re.compile(pattern)
                for i, line in enumerate(doc.split("\n"), 1):
                    if regex.search(line):
                        matches.append(f"{path}:{i}:{line}")
            except re.error:
                # Fallback to simple substring search
                for i, line in enumerate(doc.split("\n"), 1):
                    if pattern in line:
                        matches.append(f"{path}:{i}:{line}")
        
        return "\n".join(matches) if matches else f"No matches found for '{pattern}'"

    def find(self, pattern: str = "") -> str:
        """Find files by name pattern.
        
        Args:
            pattern: Glob pattern (e.g., "*.py", "test*", "main")
            
        Returns:
            List of matching file paths
        """
        # Save tree if dirty (lazy save)
        if not self._tree_saved:
            self._save_path_tree()
            self._tree_saved = True
        
        pattern = pattern.strip()
        
        if not pattern:
            return "\n".join(sorted(self._path_set))
        
        # Convert glob to regex - match anywhere in path
        regex_pattern = pattern.replace(".", r"\.").replace("*", ".*")
        regex = re.compile(regex_pattern)
        
        matches = [path for path in self._path_set if regex.search(path)]
        return "\n".join(sorted(matches)) if matches else f"No files matching '{pattern}'"

    def write(self, command: str) -> str:
        """Write a file.
        
        Args:
            command: Write command in format "path=content"
            
        Returns:
            Confirmation message
        """
        if "=" not in command:
            raise ValueError("Invalid write command. Use: write path=content")
        
        path, content = command.split("=", 1)
        path = path.strip()
        content = content.strip()
        
        # Generate unique ID
        doc_id = uuid.uuid4().hex
        
        # Check if file exists and get old ID
        existing = self.collection.get(
            where={"path": path},
        )
        
        if existing["ids"]:
            # Update existing file
            self.collection.update(
                ids=existing["ids"],
                documents=[content],
                metadatas=[{"path": path}],
            )
        else:
            # Add new file
            self.collection.add(
                ids=[doc_id],
                documents=[content],
                metadatas=[{"path": path}],
            )
            # Update in-memory cache
            self._path_set.add(path)
            parts = path.rsplit("/", 1)
            if len(parts) == 2:
                dir_path, file_name = parts
                if dir_path not in self._dir_map:
                    self._dir_map[dir_path] = []
                self._dir_map[dir_path].append(file_name)
            
            # Mark tree as dirty (save on next ls/find, not on every write)
            self._tree_saved = False
        
        return f"Written {path}"

    def read(self, path: str) -> str:
        """Read file (alias for cat).
        
        Args:
            path: File path to read
            
        Returns:
            File contents
        """
        return self.cat(path)

    def delete(self, path: str) -> str:
        """Delete a file.
        
        Args:
            path: File path to delete
            
        Returns:
            Confirmation message
            
        Raises:
            FileNotFoundError: If file doesn't exist
        """
        path = path.strip()
        
        if path not in self._path_set:
            raise FileNotFoundError(f"rm: cannot remove '{path}': No such file or directory")
        
        # Get and delete from ChromaDB
        results = self.collection.get(
            where={"path": path},
        )
        
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
        
        # Update in-memory cache
        self._path_set.discard(path)
        parts = path.rsplit("/", 1)
        if len(parts) == 2:
            dir_path, file_name = parts
            if dir_path in self._dir_map:
                self._dir_map[dir_path] = [
                    f for f in self._dir_map[dir_path] if f != file_name
                ]
        self._tree_saved = False
        
        return f"Deleted {path}"

    def clear(self):
        """Clear all files from the VFS."""
        # Delete all except __path_tree__
        all_files = self.collection.get(include=["metadatas"])
        ids_to_delete = [
            doc_id for doc_id, meta in zip(all_files["ids"], all_files["metadatas"])
            if meta.get("path") != "__path_tree__"
        ]
        
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)
        
        # Clear in-memory cache
        self._path_set.clear()
        self._dir_map.clear()

    def list_all(self) -> List[str]:
        """List all file paths.
        
        Returns:
            List of all file paths
        """
        return sorted(self._path_set)

    def stats(self) -> Dict[str, Any]:
        """Get VFS statistics.
        
        Returns:
            Dictionary with file count, total size, etc.
        """
        all_files = self.collection.get(include=["documents", "metadatas"])
        total_size = sum(len(doc) for doc in all_files["documents"])
        
        return {
            "total_files": len(self._path_set),
            "total_size": total_size,
            "directories": len(self._dir_map),
            "db_path": self.db_path,
        }
