"""Custom exceptions for LMDB VFS."""


class VFSError(Exception):
    """Base exception for VFS errors."""
    pass


class FileNotFound(VFSError):
    """File not found in the virtual filesystem."""
    pass


class PathError(VFSError):
    """Invalid path operation."""
    pass


class PermissionError(VFSError):
    """Permission denied for operation."""
    pass
