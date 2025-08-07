# Local Browser Agent - The Simplest Way to Build Browser Automation

**Run a fully local, open-source browser agent in <5 minutes.** No API keys. No cloud dependencies. Just pure, hackable browser automation.

```python
# This is all you need:
agent = BrowserAgent(task="Book a flight from NYC to Tokyo")
await agent.run("https://google.com/flights")
```

> _"Like nanoGPT, but for browser agents"_ - Built for researchers, developers, and anyone who wants simple, hackable browser automation.

## Why This Exists

Most browser automation tools are either:

- 🔒 Closed-source with expensive APIs
- 🏗️ Over-engineered with 1000s of dependencies
- ☁️ Require cloud services and API keys
- 📚 Too complex to understand or modify

**This is different.** One file. Pure Python. Runs 100% locally. You can read the entire codebase in 20 minutes.

## Features

- **624 lines of code** - Entire agent in one readable file
- **100% local** - Ollama for LLMs, no external APIs needed
- **Actually works** - Successfully completes web automation tasks
- **No BS** - No abstractions, frameworks, or enterprise patterns
- **Hackable** - Modify and experiment without diving through layers

## Quick Start

```bash
# 1. Clone and enter directory
git clone https://github.com/yourusername/local-browser-use.git
cd local-browser-use

# 2. Setup Python environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Install browser
patchright install chromium

# 4. Install Ollama & pull model (one-time setup)
# macOS/Linux: curl -fsSL https://ollama.ai/install.sh | sh
# Windows: Download from https://ollama.ai/download
ollama pull gpt-oss:20b  # Default model (good balance)
# or: ollama pull qwen3:32b  # Better performance
# or: ollama pull gpt-oss:120b  # Best performance (requires more VRAM)

# 5. Run your first automation!
python main.py
```

That's it. No API keys, no configuration files, no complex setup.

## What Can It Do?

```python
# Extract data from any website
agent = BrowserAgent(task="Find all Python job postings on HackerNews")

# Automate complex workflows
agent = BrowserAgent(task="Book the cheapest flight from NYC to SF next Friday")

# Research assistance
agent = BrowserAgent(task="Find and summarize the latest papers on LLM agents")

# E-commerce automation
agent = BrowserAgent(task="Find the best rated mechanical keyboard under $100")
```

### Quick Demo

```bash
# Watch it search the web
python main.py

# Or create your own task
python -c "
import asyncio
from main import BrowserAgent

async def run_task():
    agent = BrowserAgent(task='Find the top Show HN post today')
    result = await agent.run('https://news.ycombinator.com')
    print(result)

asyncio.run(run_task())
"
```

## WebVoyager Benchmark Support

This project includes WebVoyager benchmark support for testing and evaluation:

```bash
# Run the full WebVoyager benchmark
cd webvoyager_benchmark/reproducibility/
python webvoyager_runner.py

# Run a single task
python task_runner.py --task_id 123

# View results
python view_results.py
```

The benchmark tests various web automation scenarios to help evaluate and improve the agent's performance.

## How It Works

```
Task → LLM reasons about DOM → Execute action → Repeat until done
```

The entire agent is **624 lines** in `main.py`:

1. **Extract DOM** - JavaScript finds all interactive elements
2. **Number elements** - `[1] Search box`, `[2] Submit button`
3. **LLM decides** - "I need to click element [2]"
4. **Execute action** - Click, type, scroll, etc.
5. **Repeat** - Until task complete or timeout

No magic. No frameworks. Just a loop that works.

## Contributing

This is meant to be hacked on. Some ideas:

- **Add vision** - Use Ollama's vision models for better element detection
- **Improve prompts** - Better reasoning, fewer steps
- **New actions** - Drag & drop, file uploads, etc.
- **Speed optimizations** - Parallel DOM extraction, caching
- **New benchmarks** - Test on your own tasks

PRs welcome. Keep it simple.

## Troubleshooting

<details>
<summary>Ollama not connecting?</summary>

```bash
# Make sure ollama is running
ollama serve

# Test connection
curl http://localhost:11434/api/tags
```

</details>

<details>
<summary>Browser won't launch?</summary>

```bash
# Reinstall with anti-detection patches
patchright install chromium --force
```

</details>

<details>
<summary>Need GPU acceleration?</summary>

Ollama automatically uses GPU if available. For CPU-only:

```bash
ollama run gpt-oss:20b  # Good balance for CPU/GPU
```

</details>

## Performance Notes

This agent is designed for research and experimentation. Performance varies based on:

- **Model choice**: Larger models (gpt-oss:120b) generally perform better
- **Hardware**: GPU acceleration improves response times
- **Task complexity**: Simple tasks work better than complex multi-step workflows
- **Website design**: Modern, well-structured sites are easier to navigate

_Performance testing is ongoing. Contributions to benchmark results are welcome._

## Star History

If this project is useful to you, please give it a star!

## License

MIT - Do whatever you want with it.

---

**Built by the open-source community**  
Contribution guidelines: _Just write good code._