"""Tests for MemoryAwareAgent."""

import pytest
import tempfile
import shutil

from reasoning_fs.agent import MemoryAwareAgent
from reasoning_fs.memory import ReasoningMemory
from reasoning_fs.vfs import ChromaFs


@pytest.fixture
def temp_db():
    """Create a temporary database path."""
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)


@pytest.fixture
def agent(temp_db):
    """Create a MemoryAwareAgent with temp databases."""
    memory = ReasoningMemory(db_path=temp_db)
    vfs = ChromaFs(db_path=temp_db)
    return MemoryAwareAgent(memory=memory, fs=vfs)


class TestMemoryAwareAgent:
    """Tests for MemoryAwareAgent class."""

    def test_init(self, agent):
        """Test initialization."""
        assert agent.memory is not None
        assert agent.fs is not None
        assert agent.scaler is not None
        assert agent.confidence_threshold == 0.5

    def test_run(self, agent):
        """Test running a task."""
        result = agent.run("Find SQL injection")
        
        assert "Executed task" in result
        assert "confidence" in result.lower()

    def test_explore_grep(self, agent):
        """Test exploring with grep."""
        # First write a file
        agent.fs.write("test.txt=SELECT * FROM users")
        
        result = agent.explore("grep SELECT")
        assert "test.txt" in result
        assert "SELECT" in result

    def test_explore_cat(self, agent):
        """Test exploring with cat."""
        agent.fs.write("test.txt=Hello World")
        
        result = agent.explore("cat test.txt")
        assert result == "Hello World"

    def test_explore_ls(self, agent):
        """Test exploring with ls."""
        agent.fs.write("src/main.py=print('hello')")
        agent.fs.write("README.md=# Project")
        
        result = agent.explore("ls")
        assert "src" in result or "README.md" in result

    def test_explore_find(self, agent):
        """Test exploring with find."""
        agent.fs.write("src/main.py=print('hello')")
        agent.fs.write("tests/test_main.py=def test(): pass")
        
        result = agent.explore("find *.py")
        assert "src/main.py" in result

    def test_explore_unknown_command(self, agent):
        """Test exploring with unknown command."""
        result = agent.explore("unknown_command")
        assert "Unknown command" in result

    def test_memory_logging(self, agent):
        """Test that agent logs to memory."""
        agent.run("Test task")
        
        stats = agent.memory.stats()
        assert stats["total_traces"] >= 1

    def test_vfs_persistence(self, temp_db):
        """Test that VFS persists across agent instances."""
        # Create first agent
        memory1 = ReasoningMemory(db_path=temp_db)
        vfs1 = ChromaFs(db_path=temp_db)
        agent1 = MemoryAwareAgent(memory=memory1, fs=vfs1)
        
        agent1.fs.write("test.txt=Content")
        
        # Create second agent with same DB
        memory2 = ReasoningMemory(db_path=temp_db)
        vfs2 = ChromaFs(db_path=temp_db)
        agent2 = MemoryAwareAgent(memory=memory2, fs=vfs2)
        
        # Should be able to read the file
        content = agent2.fs.cat("test.txt")
        assert content == "Content"
