"""UNIX command interpreter for VFS (Mintlify pattern).

Enables LLMs to use native shell commands without special training.
Supports: ls, cat, grep, find, cd, pwd, mkdir, rm, cp, mv, head, tail, wc
"""

import shlex
import re
from typing import List, Dict, Optional, Tuple, Union
from pathlib import Path as Pathlib
from .vfs import VFS
from .errors import FileNotFound, PathError, VFSError


class VFSShell:
    """UNIX-like shell interface for VFS.
    
    Translates shell commands into VFS operations.
    LLMs can use this without any special training.
    
    Example:
        >>> vfs = VFS("mydb.lmdb")
        >>> shell = VFSShell(vfs)
        >>> shell.execute("ls /docs")
        ['file1.txt', 'file2.py']
        >>> shell.execute("cat /docs/file1.txt")
        'Hello, World!'
        >>> shell.execute("grep 'hello' /docs')
        ['/docs/file1.txt:1:Hello world']
    """
    
    def __init__(self, vfs: VFS, initial_cwd: str = "."):
        """Initialize shell with VFS backend.
        
        Args:
            vfs: VFS instance to use for operations.
            initial_cwd: Initial working directory.
        """
        self.vfs = vfs
        self._cwd = "."  # Initialize first
        self._cwd = self._normalize_path(initial_cwd)
        
    def _normalize_path(self, path: str) -> str:
        """Normalize path relative to cwd."""
        path = path.strip()
        
        # Handle absolute paths
        if path.startswith("/"):
            return path[1:]  # Remove leading slash
        
        # Handle relative paths
        if path.startswith("./"):
            path = path[2:]
        
        # Join with cwd
        if self._cwd != ".":
            return f"{self._cwd}/{path}"
        return path
    
    def _resolve_path(self, path: str) -> str:
        """Resolve path with cd support."""
        # Handle cd command specially
        if path == "..":
            if self._cwd == ".":
                return "."
            return str(Pathlib(self._cwd).parent)
        elif path == ".":
            return self._cwd
        elif path.startswith("../"):
            parent = str(Pathlib(self._cwd).parent) if self._cwd != "." else "."
            return f"{parent}/{path[3:]}".replace("//", "/").strip("/") or "."
        else:
            return self._normalize_path(path)
    
    def execute(self, command: str) -> Union[str, List[str], List[Tuple[str, int, str]]]:
        """Execute a shell command.
        
        Args:
            command: Shell command string (e.g., "ls /docs", "cat file.txt").
        
        Returns:
            Command output as string, list, or list of tuples.
        
        Raises:
            VFSError: If command is unknown or fails.
        """
        command = command.strip()
        if not command:
            return ""
        
        # Parse command
        try:
            parts = shlex.split(command)
        except ValueError:
            # Fallback for simple commands
            parts = command.split()
        
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # Route to appropriate handler
        handlers = {
            "ls": self._cmd_ls,
            "dir": self._cmd_ls,
            "cat": self._cmd_cat,
            "head": self._cmd_head,
            "tail": self._cmd_tail,
            "grep": self._cmd_grep,
            "find": self._cmd_find,
            "cd": self._cmd_cd,
            "pwd": self._cmd_pwd,
            "mkdir": self._cmd_mkdir,
            "rm": self._cmd_rm,
            "cp": self._cmd_cp,
            "mv": self._cmd_mv,
            "touch": self._cmd_touch,
            "wc": self._cmd_wc,
            "echo": self._cmd_echo,
            "help": self._cmd_help,
        }
        
        handler = handlers.get(cmd)
        if not handler:
            raise VFSError(f"Unknown command: {cmd}. Run 'help' for available commands.")
        
        return handler(args)
    
    # ========== Command Handlers ==========
    
    def _cmd_ls(self, args: List[str]) -> List[str]:
        """ls [path] - List directory contents."""
        path = args[0] if args else self._cwd
        path = self._resolve_path(path)
        
        try:
            items = self.vfs.listdir(path)
            return items
        except PathError as e:
            raise VFSError(f"ls: {e}")
    
    def _cmd_cat(self, args: List[str]) -> str:
        """cat [path] - Display file contents."""
        if not args:
            raise VFSError("cat: missing file argument")
        
        path = self._resolve_path(args[0])
        
        try:
            content = self.vfs.read(path)
            return content
        except FileNotFound:
            raise VFSError(f"cat: {path}: No such file")
    
    def _cmd_head(self, args: List[str]) -> str:
        """head [-n lines] [path] - Display first lines of file."""
        n = 10
        path = None
        
        # Parse arguments
        i = 0
        while i < len(args):
            if args[i] == "-n" and i + 1 < len(args):
                n = int(args[i + 1])
                i += 2
            elif not args[i].startswith("-"):
                path = args[i]
                i += 1
            else:
                i += 1
        
        if not path:
            raise VFSError("head: missing file argument")
        
        path = self._resolve_path(path)
        
        try:
            content = self.vfs.read(path)
            lines = content.split("\n")[:n]
            return "\n".join(lines)
        except FileNotFound:
            raise VFSError(f"head: {path}: No such file")
    
    def _cmd_tail(self, args: List[str]) -> str:
        """tail [-n lines] [path] - Display last lines of file."""
        n = 10
        path = None
        
        i = 0
        while i < len(args):
            if args[i] == "-n" and i + 1 < len(args):
                n = int(args[i + 1])
                i += 2
            elif not args[i].startswith("-"):
                path = args[i]
                i += 1
            else:
                i += 1
        
        if not path:
            raise VFSError("tail: missing file argument")
        
        path = self._resolve_path(path)
        
        try:
            content = self.vfs.read(path)
            lines = content.split("\n")[-n:]
            return "\n".join(lines)
        except FileNotFound:
            raise VFSError(f"tail: {path}: No such file")
    
    def _cmd_grep(self, args: List[str]) -> List[str]:
        """grep 'pattern' [path] - Search for pattern in files."""
        if not args:
            raise VFSError("grep: missing pattern argument")
        
        pattern = args[0]
        path = args[1] if len(args) > 1 else None
        
        if path:
            path = self._resolve_path(path)
        
        try:
            results = self.vfs.grep(pattern, path)
            # Format as grep output: "path:line_num:line"
            return [f"{p}:{ln}:{line}" for p, ln, line in results]
        except VFSError as e:
            raise VFSError(f"grep: {e}")
    
    def _cmd_find(self, args: List[str]) -> List[str]:
        """find [path] -name 'pattern' - Find files matching pattern."""
        path = None
        pattern = "*"
        
        i = 0
        while i < len(args):
            if args[i] == "-name" and i + 1 < len(args):
                pattern = args[i + 1]
                i += 2
            elif not args[i].startswith("-"):
                path = args[i]
                i += 1
            else:
                i += 1
        
        if path:
            path = self._resolve_path(path)
        
        try:
            results = self.vfs.find(pattern, path)
            # Format paths with leading slash
            return [f"/{p}" for p in results]
        except VFSError as e:
            raise VFSError(f"find: {e}")
    
    def _cmd_cd(self, args: List[str]) -> str:
        """cd [path] - Change working directory."""
        if not args:
            # cd without args goes to root
            self._cwd = "."
            return ""
        
        path = args[0]
        
        if path == "~":
            path = "."
        
        path = self._resolve_path(path)
        
        # Check if it's a directory
        if not self.vfs.exists(path):
            raise VFSError(f"cd: {path}: No such directory")
        
        # Verify it's a directory (not a file)
        try:
            self.vfs.listdir(path)
            self._cwd = path
            return ""
        except PathError:
            raise VFSError(f"cd: {path}: Not a directory")
    
    def _cmd_pwd(self, args: List[str]) -> str:
        """pwd - Print working directory."""
        return f"/{self._cwd}" if self._cwd != "." else "/"
    
    def _cmd_mkdir(self, args: List[str]) -> str:
        """mkdir [path] - Create directory."""
        if not args:
            raise VFSError("mkdir: missing directory argument")
        
        path = self._resolve_path(args[0])
        
        try:
            self.vfs.mkdir(path)
            return ""
        except VFSError as e:
            raise VFSError(f"mkdir: {e}")
    
    def _cmd_rm(self, args: List[str]) -> str:
        """rm [path] - Remove file."""
        if not args:
            raise VFSError("rm: missing file argument")
        
        path = self._resolve_path(args[0])
        
        try:
            self.vfs.delete(path)
            return ""
        except FileNotFound:
            raise VFSError(f"rm: {path}: No such file")
    
    def _cmd_cp(self, args: List[str]) -> str:
        """cp [src] [dst] - Copy file."""
        if len(args) < 2:
            raise VFSError("cp: source and destination required")
        
        src = self._resolve_path(args[0])
        dst = self._resolve_path(args[1])
        
        try:
            content = self.vfs.read(src)
            self.vfs.write(dst, content)
            return ""
        except FileNotFound:
            raise VFSError(f"cp: {src}: No such file")
    
    def _cmd_mv(self, args: List[str]) -> str:
        """mv [src] [dst] - Move/rename file."""
        if len(args) < 2:
            raise VFSError("mv: source and destination required")
        
        src = self._resolve_path(args[0])
        dst = self._resolve_path(args[1])
        
        try:
            content = self.vfs.read(src)
            self.vfs.write(dst, content)
            self.vfs.delete(src)
            return ""
        except FileNotFound:
            raise VFSError(f"mv: {src}: No such file")
    
    def _cmd_touch(self, args: List[str]) -> str:
        """touch [path] - Create empty file."""
        if not args:
            raise VFSError("touch: missing file argument")
        
        path = self._resolve_path(args[0])
        
        # Create parent directories if needed
        parent = str(Pathlib(path).parent)
        if parent != "." and not self.vfs.exists(parent):
            self.vfs.mkdir(parent)
        
        # Create empty file (or update timestamp if exists)
        try:
            self.vfs.write(path, "")
        except VFSError:
            pass  # File may already exist, that's OK
        
        return ""
    
    def _cmd_wc(self, args: List[str]) -> str:
        """wc [path] - Word count."""
        if not args:
            raise VFSError("wc: missing file argument")
        
        path = self._resolve_path(args[0])
        
        try:
            content = self.vfs.read(path)
            lines = content.count("\n") + 1
            words = len(content.split())
            chars = len(content)
            return f"{lines} {words} {chars} {path}"
        except FileNotFound:
            raise VFSError(f"wc: {path}: No such file")
    
    def _cmd_echo(self, args: List[str]) -> str:
        """echo [text] - Display text."""
        return " ".join(args)
    
    def _cmd_help(self, args: List[str]) -> str:
        """help - Show available commands."""
        return """
Available commands:
  ls [path]        - List directory contents
  cat [path]       - Display file contents
  head [-n N] [path] - Display first N lines (default: 10)
  tail [-n N] [path] - Display last N lines (default: 10)
  grep 'pattern' [path] - Search for pattern in files
  find [path] -name 'pattern' - Find files matching pattern
  cd [path]        - Change working directory
  pwd              - Print working directory
  mkdir [path]     - Create directory
  rm [path]        - Remove file
  cp [src] [dst]   - Copy file
  mv [src] [dst]   - Move/rename file
  touch [path]     - Create empty file
  wc [path]        - Word count
  echo [text]      - Display text
  help             - Show this help
"""
    
    @property
    def cwd(self) -> str:
        """Get current working directory."""
        return self._cwd
    
    @cwd.setter
    def cwd(self, path: str):
        """Set current working directory."""
        self._cwd = self._resolve_path(path)


# Export for convenience
__all__ = ["VFSShell"]
