# ReasoningFS

**Memory-aware agent harness combining Google's ReasoningBank and Mintlify's ChromaFs patterns.**

```bash
pip install reasoning-fs
```

## What It Is

ReasoningFS is a lightweight Python package that gives AI agents:

1. **Memory** - Store and retrieve reasoning traces (from [ReasoningBank](https://github.com/google-research/reasoning-bank))
2. **Virtual Filesystem** - UNIX-like commands over ChromaDB (from [ChromaFs](https://github.com/mintlify/chromafs))
3. **Dynamic Scaling** - Adjust token budget/temperature based on confidence

No Docker. No containerization. Just pure vector DB magic.

## Why It Matters

Traditional agent sandboxes (like Docker-based code exec) are:
- 🐢 **Slow**: ~46,000ms per command (container startup + exec)
- 💸 **Expensive**: ~$0.10 per query
- 🔒 **Complex**: Container orchestration overhead

ReasoningFS is:
- ⚡ **Fast**: 0.006ms-600ms depending on sync strategy (76x-7,600,000x speedup)
- 💰 **Cheap**: ~$0.001 per query (100x cheaper)
- 🎯 **Simple**: Pure Python + ChromaDB

## Quick Start

### 1. Initialize

```python
from reasoning_fs import ReasoningMemory, ChromaFs, MemoryAwareAgent

memory = ReasoningMemory(db_path="reasoning_db")
vfs = ChromaFs(db_path="vfs_db")
agent = MemoryAwareAgent(memory=memory, fs=vfs)
```

### 2. Populate VFS

```python
vfs.write("src/auth/login.py="""
def login(username, password):
    # VULNERABILITY: SQL injection
    query = f"SELECT * FROM users WHERE username = '{username}'"
    return db.execute(query)
""")

vfs.write("src/auth/register.py="""
def register(username, password):
    # Secure: parameterized query
    query = "INSERT INTO users (username, password) VALUES (?, ?)"
    return db.execute(query, (username, password))
""")
```

### 3. Search & Analyze

```python
# Grep for patterns
results = vfs.grep("SELECT")
print(results)
# src/auth/login.py:3: query = f"SELECT * FROM users..."

# Read file
content = vfs.cat("src/auth/login.py")

# List directory
files = vfs.ls("src/auth/")
```

### 4. Memory-Aware Agent

```python
task = "Find SQL injection vulnerabilities"

# Agent queries memory first
similar = memory.search(task)
confidence = agent.scaler.calculate_confidence(similar)

# Adjust token budget
scaling = agent.scaler.scale(confidence)
print(f"Confidence: {confidence:.2f}")
print(f"Max tokens: {scaling.max_tokens}")
print(f"Temperature: {scaling.temperature}")

# Execute task
result = agent.run(task)

# Log reasoning trace
memory.store(
    task=task,
    reasoning="Searched for SELECT statements, found f-string interpolation",
    outcome="Found vulnerability in login.py",
    success=True
)
```

## CLI Usage

```bash
# Initialize databases
reasoning-fs init --memory reasoning_db --vfs vfs_db

# Store a reasoning trace
reasoning-fs store "Find SQL injection" "Searched for SELECT" "Found in login.py" --success

# Search memory
reasoning-fs search "Find auth bugs" --n 5

# VFS commands
reasoning-fs write "test.txt=Hello World"
reasoning-fs cat test.txt
reasoning-fs grep "SELECT"
reasoning-fs ls src/
reasoning-fs find "*.py"

# Get scaling params
reasoning-fs scale 0.8

# View stats
reasoning-fs stats
```

## LangChain Integration

```python
from langchain.llms import OpenAI
from reasoning_fs.langchain import create_reasoning_fs_agent

llm = OpenAI()
tools = [ReasoningFsTool()]

agent = create_reasoning_fs_agent(llm, tools)
result = agent.run("Find SQL injection in src/")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      MemoryAwareAgent                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐                 │
│  │  ReasoningMemory│    │     ChromaFs    │                 │
│  │  (reasoning_db) │    │    (vfs_db)     │                 │
│  │                 │    │                 │                 │
│  │  - Store traces │    │  - Files as     │                 │
│  │  - Search       │    │    documents    │                 │
│  │  - Aggregate    │    │  - grep/cat/ls  │                 │
│  └────────┬────────┘    └────────┬────────┘                 │
│           │                      │                          │
│           └──────────┬───────────┘                          │
│                      │                                       │
│           ┌──────────▼───────────┐                          │
│           │  ConfidenceScaler    │                          │
│           │                      │                          │
│           │  - Calculate confidence                        │
│           │  - Scale tokens/temp  │                          │
│           └──────────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
```

## Components

### ReasoningMemory
Stores reasoning traces as embeddings in ChromaDB:
- `store(task, reasoning, outcome, success)` - Log a trace
- `search(query, n_results)` - Find similar traces
- `aggregate(trace_ids)` - Summarize multiple traces

### ChromaFs
Virtual filesystem over ChromaDB:
- `write(path=content)` - Write file
- `cat(path)` - Read file
- `grep(pattern)` - Search for pattern
- `ls(path)` - List directory
- `find(pattern)` - Find files

### ConfidenceScaler
Dynamic scaling based on memory:
- `calculate_confidence(similar_traces)` - Score 0.0-1.0
- `scale(confidence)` - Return ScalingParams
- `get_recommendation(confidence)` - Human-readable advice

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=reasoning_fs --cov-report=term-missing

# Run linter
ruff check reasoning_fs/ tests/

# Run type checker
mypy reasoning_fs/ --ignore-missing-imports
```

## Performance

| Scenario | Latency | Notes |
|----------|---------|-------|
| Memory write (async) | ~0.006ms/file | Volatile, batch-sync later |
| ChromaFs sync write | ~600ms/file | Persisted to disk |
| Cache read (hit) | ~0.003ms/file | From memory buffer |
| DB read (miss) | ~3ms/file | Fallback to ChromaDB |
| Batch sync (100 files) | ~1,700ms | ~17ms/file amortized |

**Speedup vs Docker**: 76x (sync write) to 7,600,000x (memory write) depending on strategy.

**Trade-off**: AsyncOverlayFs trades *immediate persistence* for *instant writes*. Best for agents that:
1. Write many files to memory buffer (instant)
2. Read frequently from cache (instant)
3. Sync to disk in batches (amortized cost)

**Bottleneck**: ChromaDB sync I/O, not the async layer. For true parallelism, need async vector DB (Qdrant, Weaviate).

## Benchmarks

Ready to test on:
- **SWE-Bench** - Software engineering tasks
- **WebArena** - Web navigation
- Custom benchmarks

```python
from reasoning_fs import MemoryAwareAgent, ReasoningMemory, ChromaFs

# Run benchmark
memory = ReasoningMemory("benchmark_db")
vfs = ChromaFs("benchmark_db")
agent = MemoryAwareAgent(memory, vfs)

results = []
for task in benchmark_tasks:
    result = agent.run(task)
    results.append(result)

# Calculate metrics
success_rate = sum(1 for r in results if r.success) / len(results)
print(f"Success rate: {success_rate:.2%}")
```

## Roadmap

- [ ] Add more VFS commands (rm, mv, cp, chmod)
- [ ] Async support for `_arun` methods
- [ ] Integration with AutoGen, CrewAI
- [ ] Distributed memory (Redis, PostgreSQL)
- [ ] Web UI for browsing traces
- [ ] Benchmark suite (SWE-Bench, WebArena)

## License

MIT

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/ -v`
5. Submit a PR

## References

- [ReasoningBank](https://github.com/google-research/reasoning-bank) - Google's memory mechanism
- [ChromaFs](https://github.com/mintlify/chromafs) - Mintlify's VFS pattern
- [SWE-Bench](https://www.swebench.com/) - Software engineering benchmark
- [WebArena](https://webarena.dev/) - Web navigation benchmark
