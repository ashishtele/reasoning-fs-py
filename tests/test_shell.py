"""Tests for UNIX shell interface."""

import pytest
from lmdb_vfs import VFS
from lmdb_vfs.shell import VFSShell


class TestVFSShell:
    """Test shell command execution."""
    
    @pytest.fixture
    def vfs(self, tmp_path):
        """Create test VFS."""
        db_path = str(tmp_path / "test.lmdb")
        vfs = VFS(db_path)
        
        # Setup test files
        vfs.write("docs/file1.txt", "Hello, World!\nLine 2\nLine 3")
        vfs.write("docs/file2.py", "print('hello')\nprint('world')")
        vfs.write("src/main.py", "def main():\n    print('main')")
        vfs.mkdir("src/utils")
        vfs.write("src/utils/helper.py", "def helper():\n    pass")
        
        yield vfs
        vfs.close()
    
    @pytest.fixture
    def shell(self, vfs):
        """Create shell with test VFS."""
        return VFSShell(vfs)
    
    def test_ls_root(self, shell):
        """Test ls at root."""
        result = shell.execute("ls /")
        assert "docs" in result
        assert "src" in result
    
    def test_ls_dir(self, shell):
        """Test ls on directory."""
        result = shell.execute("ls /docs")
        assert "file1.txt" in result
        assert "file2.py" in result
    
    def test_cat_file(self, shell):
        """Test cat command."""
        result = shell.execute("cat /docs/file1.txt")
        assert "Hello, World!" in result
        assert "Line 2" in result
    
    def test_head(self, shell):
        """Test head command."""
        result = shell.execute("head -n 2 /docs/file1.txt")
        lines = result.split("\n")
        assert len(lines) == 2
        assert "Hello, World!" in lines[0]
    
    def test_tail(self, shell):
        """Test tail command."""
        result = shell.execute("tail -n 2 /docs/file1.txt")
        lines = result.split("\n")
        assert len(lines) == 2
        assert "Line 3" in lines[-1]
    
    def test_grep(self, shell):
        """Test grep command."""
        result = shell.execute("grep 'hello' /docs")
        assert len(result) > 0
        assert any("file2.py" in r for r in result)
    
    def test_find(self, shell):
        """Test find command."""
        result = shell.execute("find / -name '*.py'")
        assert any("main.py" in r for r in result)
        assert any("helper.py" in r for r in result)
    
    def test_cd_pwd(self, shell):
        """Test cd and pwd."""
        assert shell.cwd == "."
        
        shell.execute("cd /docs")
        assert shell.cwd == "docs"
        
        result = shell.execute("pwd")
        assert result == "/docs"
    
    def test_mkdir(self, shell):
        """Test mkdir command."""
        shell.execute("mkdir /test_dir")
        assert shell.vfs.exists("test_dir")
    
    def test_rm(self, shell):
        """Test rm command."""
        shell.execute("touch /tmp/test.txt")
        assert shell.vfs.exists("tmp/test.txt")
        
        shell.execute("rm /tmp/test.txt")
        assert not shell.vfs.exists("tmp/test.txt")
    
    def test_cp(self, shell):
        """Test cp command."""
        shell.execute("cp /docs/file1.txt /tmp/copy.txt")
        assert shell.vfs.exists("tmp/copy.txt")
        
        original = shell.vfs.read("docs/file1.txt")
        copy = shell.vfs.read("tmp/copy.txt")
        assert original == copy
    
    def test_mv(self, shell):
        """Test mv command."""
        shell.execute("touch /tmp/original.txt")
        shell.execute("mv /tmp/original.txt /tmp/renamed.txt")
        
        assert not shell.vfs.exists("tmp/original.txt")
        assert shell.vfs.exists("tmp/renamed.txt")
    
    def test_touch(self, shell):
        """Test touch command."""
        shell.execute("touch /tmp/newfile.txt")
        assert shell.vfs.exists("tmp/newfile.txt")
    
    def test_wc(self, shell):
        """Test wc command."""
        result = shell.execute("wc /docs/file1.txt")
        parts = result.split()
        assert len(parts) == 4  # lines words chars filename
        assert parts[0] == "3"  # 3 lines
    
    def test_echo(self, shell):
        """Test echo command."""
        result = shell.execute("echo Hello World")
        assert result == "Hello World"
    
    def test_unknown_command(self, shell):
        """Test unknown command error."""
        with pytest.raises(Exception) as exc_info:
            shell.execute("unknown_command")
        assert "Unknown command" in str(exc_info.value)
    
    def test_cd_relative(self, shell):
        """Test relative path cd."""
        shell.execute("cd /src")
        shell.execute("cd utils")
        assert shell.cwd == "src/utils"
    
    def test_cd_parent(self, shell):
        """Test cd .."""
        shell.execute("cd /src/utils")
        shell.execute("cd ..")
        assert shell.cwd == "src"
    
    def test_cat_nonexistent(self, shell):
        """Test cat on nonexistent file."""
        with pytest.raises(Exception) as exc_info:
            shell.execute("cat /nonexistent.txt")
        assert "No such file" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
