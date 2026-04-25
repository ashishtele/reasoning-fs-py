"""Tests for ChromaFs."""

import pytest
import tempfile
import shutil

from reasoning_fs.vfs import ChromaFs


@pytest.fixture
def temp_db():
    """Create a temporary database path."""
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path)


class TestChromaFs:
    """Tests for ChromaFs class."""

    def test_init(self, temp_db):
        """Test initialization."""
        vfs = ChromaFs(db_path=temp_db)
        assert vfs.db_path == temp_db
        assert vfs.collection.count() == 0

    def test_write(self, temp_db):
        """Test writing a file."""
        vfs = ChromaFs(db_path=temp_db)
        result = vfs.write("test.txt=Hello, World!")
        
        assert "Written" in result
        assert vfs.collection.count() == 1

    def test_write_invalid(self, temp_db):
        """Test writing with invalid command."""
        vfs = ChromaFs(db_path=temp_db)
        
        with pytest.raises(ValueError):
            vfs.write("invalid_command")

    def test_cat(self, temp_db):
        """Test reading a file."""
        vfs = ChromaFs(db_path=temp_db)
        vfs.write("test.txt=Hello, World!")
        
        content = vfs.cat("test.txt")
        assert content == "Hello, World!"

    def test_cat_not_found(self, temp_db):
        """Test reading non-existent file."""
        vfs = ChromaFs(db_path=temp_db)
        
        with pytest.raises(FileNotFoundError):
            vfs.cat("nonexistent.txt")

    def test_read_alias(self, temp_db):
        """Test read() as alias for cat()."""
        vfs = ChromaFs(db_path=temp_db)
        vfs.write("test.txt=Content")
        
        content = vfs.read("test.txt")
        assert content == "Content"

    def test_ls(self, temp_db):
        """Test listing directory."""
        vfs = ChromaFs(db_path=temp_db)
        vfs.write("src/main.py=print('hello')")
        vfs.write("src/utils.py=def util(): pass")
        vfs.write("README.md=# Project")
        
        # List root
        result = vfs.ls("")
        assert "src" in result
        assert "README.md" in result

    def test_grep(self, temp_db):
        """Test searching for pattern."""
        vfs = ChromaFs(db_path=temp_db)
        vfs.write("src/main.py=SELECT * FROM users")
        vfs.write("src/utils.py=INSERT INTO logs")
        vfs.write("README.md=No SQL here")
        
        result = vfs.grep("SELECT")
        assert "src/main.py" in result
        assert "SELECT" in result

    def test_grep_no_match(self, temp_db):
        """Test grep with no matches."""
        vfs = ChromaFs(db_path=temp_db)
        vfs.write("test.txt=Hello World")
        
        result = vfs.grep("xyz")
        assert "No matches found" in result

    def test_find(self, temp_db):
        """Test finding files."""
        vfs = ChromaFs(db_path=temp_db)
        vfs.write("src/main.py=print('hello')")
        vfs.write("src/utils.py=def util(): pass")
        vfs.write("tests/test_main.py=def test(): pass")
        
        # Find Python files
        result = vfs.find("*.py")
        assert "src/main.py" in result
        assert "src/utils.py" in result
        assert "tests/test_main.py" in result

    def test_find_by_name(self, temp_db):
        """Test finding files by name."""
        vfs = ChromaFs(db_path=temp_db)
        vfs.write("src/main.py=print('hello')")
        vfs.write("src/utils.py=def util(): pass")
        
        result = vfs.find("main")
        assert "src/main.py" in result

    def test_delete(self, temp_db):
        """Test deleting a file."""
        vfs = ChromaFs(db_path=temp_db)
        vfs.write("test.txt=Content")
        
        assert vfs.collection.count() == 1
        
        result = vfs.delete("test.txt")
        assert "Deleted" in result
        assert vfs.collection.count() == 0

    def test_delete_not_found(self, temp_db):
        """Test deleting non-existent file."""
        vfs = ChromaFs(db_path=temp_db)
        
        with pytest.raises(FileNotFoundError):
            vfs.delete("nonexistent.txt")

    def test_list_all(self, temp_db):
        """Test listing all files."""
        vfs = ChromaFs(db_path=temp_db)
        vfs.write("src/main.py=print('hello')")
        vfs.write("tests/test_main.py=def test(): pass")
        
        files = vfs.list_all()
        assert len(files) == 2
        assert "src/main.py" in files
        assert "tests/test_main.py" in files

    def test_stats(self, temp_db):
        """Test getting statistics."""
        vfs = ChromaFs(db_path=temp_db)
        vfs.write("test.txt=Content")
        
        stats = vfs.stats()
        assert stats["total_files"] == 1
        assert stats["db_path"] == temp_db

    def test_multiple_files(self, temp_db):
        """Test with multiple files."""
        vfs = ChromaFs(db_path=temp_db)
        
        files = {
            "src/auth/login.py": "def login(): pass",
            "src/auth/register.py": "def register(): pass",
            "src/utils/db.py": "def query(): pass",
            "README.md": "# Project",
        }
        
        for path, content in files.items():
            vfs.write(f"{path}={content}")
        
        assert vfs.collection.count() == 4
        
        # Search for 'def'
        result = vfs.grep("def")
        assert result.count("\n") >= 2  # At least 3 matches
        
        # Find Python files
        py_files = vfs.find("*.py")
        assert len(py_files.split("\n")) == 3
