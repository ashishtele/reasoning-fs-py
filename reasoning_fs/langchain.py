"""LangChain integration for ReasoningFS.

Provides drop-in wrappers for LangChain agents with memory-aware scaling.
"""

from typing import Any, Dict, List, Optional, Sequence
from dataclasses import dataclass

from langchain_core.callbacks import (
    CallbackManagerForToolRun,
    AsyncCallbackManagerForToolRun,
)
from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseLanguageModel
from pydantic import Field

from .memory import ReasoningMemory
from .vfs import ChromaFs
from .scaling import ConfidenceScaler


@dataclass
class ReasoningTrace:
    """Reasoning trace for LangChain integration."""
    task: str
    reasoning: str
    outcome: str
    success: bool
    metadata: Optional[Dict[str, Any]] = None


class ReasoningFsTool(BaseTool):
    """Tool that wraps ChromaFs commands with memory-aware scaling.
    
    Example:
        >>> from reasoning_fs.langchain import ReasoningFsTool
        >>> tool = ReasoningFsTool(memory_path="db", vfs_path="db")
        >>> result = tool.run("grep -r 'auth' src/")
    """
    
    name: str = "reasoning_fs"
    description: str = (
        "Execute UNIX-like commands on a virtual filesystem with memory-aware scaling. "
        "Commands: grep, cat, ls, find, write, read. "
        "Example: 'grep -r \"pattern\" path/' or 'cat file.py'"
    )
    
    # Pydantic v2 fields - use Field with exclude=True to avoid serialization issues
    memory: ReasoningMemory = Field(default=None, exclude=True)  # type: ignore
    vfs: ChromaFs = Field(default=None, exclude=True)  # type: ignore
    scaler: ConfidenceScaler = Field(default=None, exclude=True)  # type: ignore
    
    def __init__(
        self,
        memory_path: str = "reasoning_db",
        vfs_path: str = "vfs_db",
    ):
        """Initialize with memory and VFS paths.
        
        Args:
            memory_path: Path to ReasoningMemory ChromaDB
            vfs_path: Path to ChromaFs ChromaDB
        """
        # Create instances first
        memory = ReasoningMemory(db_path=memory_path)
        vfs = ChromaFs(db_path=vfs_path)
        scaler = ConfidenceScaler()
        
        # Call parent init with all required fields - use literal strings for name/description
        super().__init__(
            name="reasoning_fs",
            description=(
                "Execute UNIX-like commands on a virtual filesystem with memory-aware scaling. "
                "Commands: grep, cat, ls, find, write, read. "
                "Example: 'grep -r \"pattern\" path/' or 'cat file.py'"
            ),
            memory=memory,
            vfs=vfs,
            scaler=scaler,
        )
    
    def _run(
        self,
        command: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        """Execute a UNIX-like command.
        
        Args:
            command: UNIX command string (e.g., "grep -r 'auth' src/")
            
        Returns:
            Command output as string
        """
        # Query memory for similar tasks
        task_desc = f"Execute: {command}"
        similar = self.memory.search(task_desc)
        confidence = self.scaler.calculate_confidence(similar)
        
        # Adjust token budget if LLM is involved
        scaling_params = self.scaler.scale(confidence)
        
        # Execute command
        try:
            if command.startswith("grep"):
                # Extract pattern from "grep pattern" command
                pattern = command[4:].strip()
                result = self.vfs.grep(pattern)
            elif command.startswith("cat"):
                # Extract path from "cat path" command
                path = command[3:].strip()
                result = self.vfs.cat(path)
            elif command.startswith("ls"):
                # Extract path from "ls path" command
                path = command[2:].strip()
                result = self.vfs.ls(path)
            elif command.startswith("find"):
                # Extract pattern from "find pattern" command
                pattern = command[4:].strip()
                result = self.vfs.find(pattern)
            elif command.startswith("write"):
                result = self.vfs.write(command)
            elif command.startswith("read"):
                # Extract path from "read path" command
                path = command[4:].strip()
                result = self.vfs.read(path)
            else:
                result = f"Unknown command: {command}"
            
            # Log reasoning trace
            self.memory.store(
                task=task_desc,
                reasoning=f"Executed {command} with confidence {confidence:.2f}",
                outcome=result[:500],  # Truncate for storage
                success=True,
                metadata={
                    "confidence": confidence,
                    "max_tokens": scaling_params.max_tokens,
                    "temperature": scaling_params.temperature,
                }
            )
            
            return result
            
        except Exception as e:
            # Log failure trace
            self.memory.store(
                task=task_desc,
                reasoning=f"Failed to execute {command}",
                outcome=str(e),
                success=False,
            )
            return f"Error: {str(e)}"
    
    async def _arun(
        self,
        command: str,
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
    ) -> str:
        """Async version of _run."""
        # For now, just call sync version
        return self._run(command, run_manager=None)


class MemoryAwareLangChainAgent:
    """Wrapper that adds memory-aware scaling to any LangChain agent.
    
    Example:
        >>> from langchain.agents import initialize_agent
        >>> from langchain.llms import OpenAI
        >>> from reasoning_fs.langchain import MemoryAwareLangChainAgent
        >>>
        >>> llm = OpenAI()
        >>> tools = [...]  # Your tools
        >>> agent = initialize_agent(tools, llm)
        >>>
        >>> # Wrap with memory
        >>> wrapped = MemoryAwareLangChainAgent(
        ...     agent=agent,
        ...     memory_path="db",
        ...     vfs_path="db"
        ... )
        >>> result = wrapped.run("Find auth bugs in src/")
    """
    
    def __init__(
        self,
        agent: Any,  # LangChain agent
        memory_path: str = "reasoning_db",
        vfs_path: str = "vfs_db",
        confidence_threshold: float = 0.5,
    ):
        """Initialize wrapper.
        
        Args:
            agent: LangChain agent to wrap
            memory_path: Path to ReasoningMemory
            vfs_path: Path to ChromaFs
            confidence_threshold: Threshold for scaling decisions
        """
        self.agent = agent
        self.memory = ReasoningMemory(db_path=memory_path)
        self.vfs = ChromaFs(db_path=vfs_path)
        self.scaler = ConfidenceScaler()
        self.confidence_threshold = confidence_threshold
    
    def run(self, input_text: str) -> str:
        """Run agent with memory-aware scaling.
        
        Args:
            input_text: Task description
            
        Returns:
            Agent output
        """
        # Query memory before running
        similar = self.memory.search(input_text)
        confidence = self.scaler.calculate_confidence(similar)
        
        # Log pre-execution trace
        self.memory.store(
            task=input_text,
            reasoning=f"Pre-execution confidence: {confidence:.2f}",
            outcome="",
            success=True,
            metadata={"pre_confidence": confidence}
        )
        
        # Run agent
        try:
            result = self.agent.run(input_text)
            
            # Log post-execution trace
            self.memory.store(
                task=input_text,
                reasoning=f"Agent completed task",
                outcome=str(result)[:500],
                success=True,
            )
            
            return result
            
        except Exception as e:
            # Log failure
            self.memory.store(
                task=input_text,
                reasoning=f"Agent failed",
                outcome=str(e),
                success=False,
            )
            raise
    
    async def arun(self, input_text: str) -> str:
        """Async version of run."""
        # For now, just call sync version
        return self.run(input_text)


def create_reasoning_fs_agent(
    llm: BaseLanguageModel,
    tools: Sequence[BaseTool],
    memory_path: str = "reasoning_db",
    vfs_path: str = "vfs_db",
    **kwargs: Any,
) -> MemoryAwareLangChainAgent:
    """Factory function to create a memory-aware LangChain agent.
    
    Example:
        >>> from langchain.llms import OpenAI
        >>> from reasoning_fs.langchain import create_reasoning_fs_agent
        >>>
        >>> llm = OpenAI()
        >>> tools = [ReasoningFsTool()]
        >>> agent = create_reasoning_fs_agent(llm, tools)
        >>> result = agent.run("Find SQL injection in login.py")
    
    Args:
        llm: LangChain LLM
        tools: Sequence of tools
        memory_path: Path to ReasoningMemory
        vfs_path: Path to ChromaFs
        **kwargs: Additional args for agent creation
        
    Returns:
        MemoryAwareLangChainAgent instance
    """
    from langchain.agents import initialize_agent, AgentType
    
    # Create base agent
    base_agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
        **kwargs
    )
    
    # Wrap with memory
    return MemoryAwareLangChainAgent(
        agent=base_agent,
        memory_path=memory_path,
        vfs_path=vfs_path,
    )


__all__ = [
    "ReasoningFsTool",
    "MemoryAwareLangChainAgent",
    "create_reasoning_fs_agent",
    "ReasoningTrace",
]
