"""Tests for ReasoningMemory."""

import pytest
import tempfile
import shutil
from pathlib import Path

from reasoning_fs.memory import ReasoningMemory, ReasoningTrace


@pytest.fixture
def temp_db():
    """Create a temporary database path."""
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)


class TestReasoningMemory:
    """Tests for ReasoningMemory class."""

    def test_init(self, temp_db):
        """Test initialization."""
        memory = ReasoningMemory(db_path=temp_db)
        assert memory.db_path == temp_db
        assert memory.collection.count() == 0

    def test_store(self, temp_db):
        """Test storing a trace."""
        memory = ReasoningMemory(db_path=temp_db)
        trace_id = memory.store(
            task="Find SQL injection",
            reasoning="Searched for SELECT statements",
            outcome="Found vulnerability in login.py",
            success=True,
            metadata={"confidence": 0.9}
        )
        
        assert trace_id is not None
        assert memory.collection.count() == 1

    def test_store_without_metadata(self, temp_db):
        """Test storing without metadata."""
        memory = ReasoningMemory(db_path=temp_db)
        trace_id = memory.store(
            task="Test task",
            reasoning="Test reasoning",
            outcome="Test outcome",
            success=False
        )
        
        assert trace_id is not None
        assert memory.collection.count() == 1

    def test_search(self, temp_db):
        """Test searching for traces."""
        memory = ReasoningMemory(db_path=temp_db)
        
        # Store some traces
        memory.store(
            task="Find SQL injection",
            reasoning="Searched for SELECT",
            outcome="Found in login.py",
            success=True
        )
        memory.store(
            task="Find auth bugs",
            reasoning="Checked login flow",
            outcome="Found weak password",
            success=True
        )
        memory.store(
            task="Find XSS",
            reasoning="Checked input validation",
            outcome="None found",
            success=False
        )
        
        # Search
        results = memory.search("Find injection")
        assert len(results) > 0
        assert "SQL injection" in results[0].task or "injection" in results[0].task.lower()

    def test_search_with_filter(self, temp_db):
        """Test searching with success filter."""
        memory = ReasoningMemory(db_path=temp_db)
        
        memory.store(
            task="Task 1",
            reasoning="Reasoning 1",
            outcome="Success",
            success=True
        )
        memory.store(
            task="Task 2",
            reasoning="Reasoning 2",
            outcome="Failure",
            success=False
        )
        
        # Filter for successful traces
        results = memory.search("Task", filter_success=True)
        assert all(t.success for t in results)

    def test_aggregate(self, temp_db):
        """Test aggregating traces."""
        memory = ReasoningMemory(db_path=temp_db)
        
        # Store traces
        ids = []
        for i in range(5):
            trace_id = memory.store(
                task=f"Task {i}",
                reasoning=f"Reasoning {i}",
                outcome=f"Outcome {i}",
                success=i < 3  # First 3 succeed
            )
            ids.append(trace_id)
        
        # Aggregate
        agg = memory.aggregate(ids)
        
        assert agg["count"] == 5
        assert agg["success_count"] == 3
        assert agg["success_rate"] == 0.6

    def test_clear(self, temp_db):
        """Test clearing memory."""
        memory = ReasoningMemory(db_path=temp_db)
        
        memory.store(
            task="Task 1",
            reasoning="Reasoning 1",
            outcome="Outcome 1",
            success=True
        )
        memory.store(
            task="Task 2",
            reasoning="Reasoning 2",
            outcome="Outcome 2",
            success=False
        )
        
        assert memory.collection.count() == 2
        
        memory.clear()
        assert memory.collection.count() == 0

    def test_stats(self, temp_db):
        """Test getting statistics."""
        memory = ReasoningMemory(db_path=temp_db)
        
        memory.store(
            task="Task 1",
            reasoning="Reasoning 1",
            outcome="Outcome 1",
            success=True
        )
        
        stats = memory.stats()
        assert stats["total_traces"] == 1
        assert stats["db_path"] == temp_db
