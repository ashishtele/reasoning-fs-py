#!/usr/bin/env python3
"""Load real data from your workspace into LMDB VFS for testing."""

import os
import sys
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from lmdb_vfs import VFS


def load_obsidian_vault(vfs: VFS, vault_path: str):
    """Load all markdown files from Obsidian vault."""
    print(f"Loading Obsidian vault from: {vault_path}")
    
    count = 0
    for root, dirs, files in os.walk(vault_path):
        for file in files:
            if file.endswith(".md"):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, vault_path)
                
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    vfs.write(rel_path, content)
                    count += 1
                    
                    if count % 10 == 0:
                        print(f"  Loaded {count} files...")
                except Exception as e:
                    print(f"  Error loading {rel_path}: {e}")
    
    print(f"✅ Loaded {count} markdown files from Obsidian vault")
    return count


def load_blog_posts(vfs: VFS, blog_path: str):
    """Load blog posts."""
    print(f"\nLoading blog posts from: {blog_path}")
    
    count = 0
    for root, dirs, files in os.walk(blog_path):
        for file in files:
            if file.endswith(".md"):
                full_path = os.path.join(root, file)
                rel_path = os.path.join("blog", os.path.relpath(full_path, blog_path))
                
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    vfs.write(rel_path, content)
                    count += 1
                except Exception as e:
                    print(f"  Error loading {rel_path}: {e}")
    
    print(f"✅ Loaded {count} blog posts")
    return count


def load_paper_files(vfs: VFS, paper_path: str):
    """Load PHUSE paper files."""
    print(f"\nLoading PHUSE paper from: {paper_path}")
    
    count = 0
    for root, dirs, files in os.walk(paper_path):
        for file in files:
            if file.endswith((".md", ".txt", ".py")):
                full_path = os.path.join(root, file)
                rel_path = os.path.join("paper", os.path.relpath(full_path, paper_path))
                
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    vfs.write(rel_path, content)
                    count += 1
                except Exception as e:
                    print(f"  Error loading {rel_path}: {e}")
    
    print(f"✅ Loaded {count} paper files")
    return count


def main():
    # Create VFS database
    db_path = "obsidian_vfs.lmdb"
    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    
    print("=" * 60)
    print("Loading Real Data into LMDB VFS")
    print("=" * 60)
    
    with VFS(db_path, map_size=1024**3) as vfs:
        # Load blog posts
        blog_path = "/home/ashish/phuse-eu-paper/blog"
        if os.path.exists(blog_path):
            load_blog_posts(vfs, blog_path)
        
        # Load paper files
        paper_path = "/home/ashish/phuse-eu-paper"
        if os.path.exists(paper_path):
            load_paper_files(vfs, paper_path)
        
        # Try to load Obsidian vault (if it exists)
        vault_path = os.path.expanduser("~/Documents/Obsidian Vault")
        if os.path.exists(vault_path):
            load_obsidian_vault(vfs, vault_path)
        else:
            print(f"\n⚠️  Obsidian vault not found at: {vault_path}")
            print("   Skipping Obsidian vault loading")
        
        # Show statistics
        print("\n" + "=" * 60)
        print("VFS Statistics")
        print("=" * 60)
        
        total_files = 0
        total_size = 0
        
        for root, dirs, files in vfs.walk("."):
            for file in files:
                total_files += 1
                # Estimate size (not accurate, but gives an idea)
                try:
                    content = vfs.read(os.path.join(root, file))
                    total_size += len(content.encode('utf-8'))
                except:
                    pass
        
        print(f"Total files: {total_files}")
        print(f"Total content size: {total_size / 1024:.1f}KB")
        
        # Test search
        print("\n" + "=" * 60)
        print("Testing Search Operations")
        print("=" * 60)
        
        # Grep for "agent"
        results = vfs.grep("agent", path="blog")
        print(f"\nGrep 'agent' in blog: {len(results)} matches")
        if results:
            print(f"  First match: {results[0][0]}:{results[0][1]}")
        
        # Find markdown files
        md_files = vfs.find("*.md", path="blog")
        print(f"\nFind *.md in blog: {len(md_files)} files")
        
        # List blog directory
        blog_items = vfs.listdir("blog")
        print(f"\nBlog directory items: {len(blog_items)}")
        print(f"  {blog_items[:5]}...")  # Show first 5
        
        # Show directory structure
        print("\n" + "=" * 60)
        print("Directory Structure")
        print("=" * 60)
        for root, dirs, files in vfs.walk("."):
            level = root.count("/") if root != "." else 0
            indent = "  " * level
            print(f"{indent}{root}/")
            sub_indent = "  " * (level + 1)
            for file in files[:3]:  # Show first 3 files
                print(f"{sub_indent}{file}")
            if len(files) > 3:
                print(f"{sub_indent}... and {len(files) - 3} more")
            break  # Just show root level


if __name__ == "__main__":
    main()
