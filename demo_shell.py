"""Demo: UNIX shell interface for VFS (Mintlify pattern).

Shows how LLMs can use native shell commands without special training.
"""

from lmdb_vfs import VFS
from lmdb_vfs.shell import VFSShell


def main():
    print("=" * 60)
    print("VFS Shell Demo - Mintlify Pattern")
    print("=" * 60)
    
    # Create VFS
    vfs = VFS("/tmp/demo_shell.lmdb")
    shell = VFSShell(vfs)
    
    # Setup test data
    print("\n1. Setting up test data...")
    vfs.write("docs/api.md", "# API Documentation\n\n## Authentication\n\nUse OAuth2.")
    vfs.write("docs/install.md", "# Installation\n\n```bash\npip install lmdb-vfs\n```")
    vfs.write("src/main.py", "from lmdb_vfs import VFS\n\ndef main():\n    vfs = VFS('db.lmdb')\n    vfs.write('test.txt', 'Hello')")
    vfs.mkdir("src/utils")
    vfs.write("src/utils/helpers.py", "def helper():\n    return 'help'")
    print("   ✓ Created 5 files")
    
    # Demo commands
    print("\n2. Running shell commands (as LLM would):")
    
    # ls
    print("\n   $ ls /")
    result = shell.execute("ls /")
    print(f"   {result}")
    
    # ls docs
    print("\n   $ ls /docs")
    result = shell.execute("ls /docs")
    print(f"   {result}")
    
    # cat
    print("\n   $ cat /docs/api.md")
    result = shell.execute("cat /docs/api.md")
    print(f"   {result[:50]}...")
    
    # grep
    print("\n   $ grep 'pip' /docs")
    result = shell.execute("grep 'pip' /docs")
    for line in result:
        print(f"   {line}")
    
    # find
    print("\n   $ find / -name '*.py'")
    result = shell.execute("find / -name '*.py'")
    for line in result:
        print(f"   {line}")
    
    # cd + pwd
    print("\n   $ cd /src")
    shell.execute("cd /src")
    print("   $ pwd")
    result = shell.execute("pwd")
    print(f"   {result}")
    
    # head
    print("\n   $ head -n 3 /src/main.py")
    result = shell.execute("head -n 3 /src/main.py")
    print(f"   {result}")
    
    # wc
    print("\n   $ wc /src/main.py")
    result = shell.execute("wc /src/main.py")
    print(f"   {result}")
    
    # cp + mv
    print("\n   $ cp /docs/api.md /tmp/api_copy.md")
    shell.execute("cp /docs/api.md /tmp/api_copy.md")
    print("   $ ls /tmp")
    result = shell.execute("ls /tmp")
    print(f"   {result}")
    
    print("\n   $ mv /tmp/api_copy.md /tmp/api_renamed.md")
    shell.execute("mv /tmp/api_copy.md /tmp/api_renamed.md")
    print("   $ ls /tmp")
    result = shell.execute("ls /tmp")
    print(f"   {result}")
    
    # Cleanup
    print("\n3. Cleanup...")
    shell.execute("rm /tmp/api_renamed.md")
    vfs.close()
    
    print("\n" + "=" * 60)
    print("✓ Demo complete! LLMs can now use native shell commands.")
    print("=" * 60)
    
    print("\nKey insight from Mintlify:")
    print("  'Teaching an agent cat /auth/oauth.mdx is trivial")
    print("   compared to teaching it to formulate the right vector query.'")
    print("\nThis is why VFS + shell interface beats RAG for agents.")


if __name__ == "__main__":
    main()
