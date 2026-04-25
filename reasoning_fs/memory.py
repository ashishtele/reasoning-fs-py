"""Reasoning memory module - stores and retrieves reasoning traces.

Based on Google's ReasoningBank: https://github.com/google-research/reasoning-bank
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import json
import uuid

import chromadb
from chromadb.config import Settings


@dataclass
class ReasoningTrace:
    """A single reasoning trace stored in memory."""
    id: str
    task: str
    reasoning: str
    outcome: str
    success: bool
    metadata: Dict[str, Any]
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningTrace":
        """Create from dictionary."""
        return cls(**data)


class ReasoningMemory:
    """Memory mechanism for agents storing reasoning traces from trajectories.
    
    Based on Google's ReasoningBank:
    - Stores reasoning traces as embeddings in ChromaDB
    - Enables similarity search for test-time scaling
    - Aggregates memory across parallel trials
    
    Example:
        >>> memory = ReasoningMemory(db_path="reasoning_db")
        >>> memory.store(
        ...     task="Find SQL injection",
        ...     reasoning="Searched for SELECT statements...",
        ...     outcome="Found vulnerability in login.py",
        ...     success=True
        ... )
        >>> similar = memory.search("Find auth bugs")
    """

    def __init__(self, db_path: str = "reasoning_db"):
        """Initialize memory with ChromaDB.
        
        Args:
            db_path: Path to ChromaDB persistence directory
        """
        self.db_path = db_path
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name="reasoning_traces",
            metadata={"description": "Reasoning traces for test-time scaling"},
        )

    def store(
        self,
        task: str,
        reasoning: str,
        outcome: str,
        success: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a reasoning trace.
        
        Args:
            task: Task description
            reasoning: Reasoning steps taken
            outcome: Result/outcome
            success: Whether the task succeeded
            metadata: Additional metadata (confidence, tokens, etc.)
            
        Returns:
            Trace ID
        """
        trace_id = str(uuid.uuid4())
        trace = ReasoningTrace(
            id=trace_id,
            task=task,
            reasoning=reasoning,
            outcome=outcome,
            success=success,
            metadata=metadata or {},
            created_at=0,  # Will be set properly
        )

        # Add to collection with task as document for embedding
        self.collection.add(
            ids=[trace_id],
            documents=[task + " " + reasoning],  # Combine for better embedding
            metadatas=[{
                "task": task,
                "reasoning": reasoning,
                "outcome": outcome,
                "success": success,
                **(metadata or {})
            }],
        )

        return trace_id

    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_success: Optional[bool] = None,
    ) -> List[ReasoningTrace]:
        """Search for similar reasoning traces.
        
        Args:
            query: Search query (task description)
            n_results: Number of results to return
            filter_success: Optional filter for success status
            
        Returns:
            List of similar ReasoningTrace objects
        """
        where = None
        if filter_success is not None:
            where = {"success": filter_success}

        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )

        traces = []
        if results["ids"] and results["ids"][0]:
            for i, trace_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i]
                traces.append(ReasoningTrace(
                    id=trace_id,
                    task=metadata.get("task", ""),
                    reasoning=metadata.get("reasoning", ""),
                    outcome=metadata.get("outcome", ""),
                    success=metadata.get("success", False),
                    metadata={k: v for k, v in metadata.items() 
                             if k not in ["task", "reasoning", "outcome", "success"]},
                    created_at=0,  # Not stored in metadata
                ))

        return traces

    def aggregate(self, traces: List[str]) -> Dict[str, Any]:
        """Aggregate multiple traces into a summary.
        
        Args:
            traces: List of trace IDs to aggregate
            
        Returns:
            Aggregation summary
        """
        traces_data = []
        for trace_id in traces:
            results = self.collection.get(ids=[trace_id])
            if results["metadatas"]:
                traces_data.append(results["metadatas"][0])

        if not traces_data:
            return {"count": 0}

        success_count = sum(1 for t in traces_data if t.get("success", False))
        
        return {
            "count": len(traces_data),
            "success_count": success_count,
            "success_rate": success_count / len(traces_data) if traces_data else 0,
            "traces": traces_data,
        }

    def clear(self):
        """Clear all traces from memory."""
        # ChromaDB requires at least one operator in where clause
        # Use a trick: delete all by matching any document
        all_ids = self.collection.get(include=["metadatas"])["ids"]
        if all_ids:
            self.collection.delete(ids=all_ids)

    def stats(self) -> Dict[str, Any]:
        """Get memory statistics."""
        count = self.collection.count()
        return {
            "total_traces": count,
            "db_path": self.db_path,
        }
