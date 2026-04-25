#!/usr/bin/env python3
"""Simple test: Load blog posts into LMDB VFS."""

import os
import sys
import shutil
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from lmdb_vfs import VFS


def main():
    db_path = "blog_vfs.lmdb"
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    
    blog_path = "/home/ashish/phuse-eu-paper/blog"
    
    print("Loading blog posts into LMDB VFS...")
    
    with VFS(db_path, map_size=1024**3) as vfs:
        count = 0
        for root, dirs, files in os.walk(blog_path):
            for file in files:
                if file.endswith(".md"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, blog_path)
                    
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    vfs.write(f"blog/{rel_path}", content)
                    count += 1
        
        print(f"✅ Loaded {count} blog posts")
        
        # Quick test
        print("\nTesting read...")
        try:
            content = vfs.read("blog/agent-framework-gap.md")
            print(f"✅ Read successful: {len(content)} chars")
        except Exception as e:
            print(f"❌ Error: {e}")
        
        # Test grep
        print("\nTesting grep for 'agent'...")
        results = vfs.grep("agent", path="blog")
        print(f"✅ Found {len(results)} matches")
        if results:
            print(f"   First: {results[0][0]}:{results[0][1]}")
        
        # Test find
        print("\nTesting find *.md...")
        files = vfs.find("*.md", path="blog")
        print(f"✅ Found {len(files)} markdown files")
        
        print(f"\n📊 Database size: {os.path.getsize(db_path) / 1024 / 1024:.2f}MB")


if __name__ == "__main__":
    main()
