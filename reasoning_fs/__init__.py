"""ReasoningFS - Memory-aware agent harness."""

from .memory import ReasoningMemory, ReasoningTrace
from .vfs import ChromaFs
from .overlay import OverlayFs
from .async_overlay import AsyncOverlayFs
from .scaling import ConfidenceScaler
from .agent import MemoryAwareAgent

__version__ = "0.2.0"
__all__ = [
    "ReasoningMemory",
    "ReasoningTrace",
    "ChromaFs",
    "OverlayFs",
    "AsyncOverlayFs",
    "ConfidenceScaler",
    "MemoryAwareAgent",
]
