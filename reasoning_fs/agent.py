"""Memory-aware agent wrapper."""

from typing import Any, Dict, List, Optional

from .memory import ReasoningMemory
from .vfs import ChromaFs
from .scaling import ConfidenceScaler


class MemoryAwareAgent:
    """Agent with memory-aware scaling.
    
    Wraps any agent with:
    - Memory query before execution
    - Confidence-based scaling
    - Reasoning trace logging
    
    Example:
        >>> memory = ReasoningMemory("db")
        >>> vfs = ChromaFs("db")
        >>> agent = MemoryAwareAgent(memory=memory, fs=vfs)
        >>> result = agent.run("Find SQL injection in src/")
    """

    def __init__(
        self,
        memory: ReasoningMemory,
        fs: ChromaFs,
        confidence_threshold: float = 0.5,
    ):
        """Initialize agent.
        
        Args:
            memory: ReasoningMemory instance
            fs: ChromaFs instance
            confidence_threshold: Threshold for confidence decisions
        """
        self.memory = memory
        self.fs = fs
        self.scaler = ConfidenceScaler()
        self.confidence_threshold = confidence_threshold

    def run(self, task: str) -> str:
        """Run agent with memory-aware scaling.
        
        Args:
            task: Task description
            
        Returns:
            Agent output
        """
        # Query memory
        similar = self.memory.search(task)
        confidence = self.scaler.calculate_confidence(similar)
        
        # Log pre-execution
        self.memory.store(
            task=task,
            reasoning=f"Pre-execution confidence: {confidence:.2f}",
            outcome="",
            success=True,
            metadata={"pre_confidence": confidence}
        )
        
        # Get scaling params
        scaling = self.scaler.scale(confidence)
        
        # Placeholder: In real implementation, pass scaling to LLM
        result = f"Executed task with confidence={confidence:.2f}, tokens={scaling.max_tokens}, temp={scaling.temperature}"
        
        # Log post-execution
        self.memory.store(
            task=task,
            reasoning=f"Task completed",
            outcome=result,
            success=True,
        )
        
        return result

    def explore(self, command: str) -> str:
        """Explore filesystem with memory logging.
        
        Args:
            command: VFS command (e.g., "grep SELECT", "cat test.txt", "ls", "find *.py")
            
        Returns:
            Command output
        """
        # Parse command
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""
        
        # Execute command
        if cmd == "grep":
            result = self.fs.grep(arg) if arg else "Usage: grep pattern"
        elif cmd == "cat":
            result = self.fs.cat(arg) if arg else "Usage: cat path"
        elif cmd == "ls":
            result = self.fs.ls(arg) if arg else self.fs.ls("")
        elif cmd == "find":
            result = self.fs.find(arg) if arg else "Usage: find pattern"
        elif cmd == "write":
            result = self.fs.write(command)  # Pass full command for write
        elif cmd == "read":
            result = self.fs.read(arg) if arg else "Usage: read path"
        else:
            result = f"Unknown command: {cmd}"
        
        # Log exploration
        self.memory.store(
            task=f"Explore: {command}",
            reasoning=f"Explored filesystem",
            outcome=result[:500],
            success=True,
        )
        
        return result
