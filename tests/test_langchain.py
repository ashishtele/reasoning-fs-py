"""Tests for LangChain integration."""

import pytest
import tempfile
import shutil

from reasoning_fs.langchain import ReasoningFsTool


@pytest.fixture
def temp_db():
    """Create a temporary database path."""
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)


class TestReasoningFsTool:
    """Tests for ReasoningFsTool class."""

    def test_init(self, temp_db):
        """Test initialization."""
        tool = ReasoningFsTool(memory_path=temp_db, vfs_path=temp_db)
        assert tool.name == "reasoning_fs"
        assert "virtual filesystem" in tool.description.lower()

    def test_run_grep(self, temp_db):
        """Test running grep command."""
        tool = ReasoningFsTool(memory_path=temp_db, vfs_path=temp_db)
        
        # First write a file
        tool.vfs.write("test.txt=SELECT * FROM users")
        
        result = tool.run("grep SELECT")
        assert "test.txt" in result
        assert "SELECT" in result

    def test_run_cat(self, temp_db):
        """Test running cat command."""
        tool = ReasoningFsTool(memory_path=temp_db, vfs_path=temp_db)
        
        tool.vfs.write("test.txt=Hello World")
        
        result = tool.run("cat test.txt")
        assert result == "Hello World"

    def test_run_unknown_command(self, temp_db):
        """Test running unknown command."""
        tool = ReasoningFsTool(memory_path=temp_db, vfs_path=temp_db)
        
        result = tool.run("unknown_command")
        assert "Unknown command" in result

    def test_memory_logging(self, temp_db):
        """Test that tool logs to memory."""
        tool = ReasoningFsTool(memory_path=temp_db, vfs_path=temp_db)
        
        tool.vfs.write("test.txt=Content")
        tool.run("cat test.txt")
        
        stats = tool.memory.stats()
        assert stats["total_traces"] >= 1
