# Squad Polyglot Benchmark Results

Running the [Aider Polyglot Benchmark](https://aider.chat/docs/leaderboards/) (225 Exercism coding problems across 6 languages) using GitHub Copilot CLI.

## Results Summary

| Language | Exercises | Pass Rate (Attempt 1) | Pass Rate (Attempt 2) | Avg Time/Exercise |
|----------|-----------|----------------------|----------------------|-------------------|
| Python | 34 | 100% (34/34) | 100% (34/34) | ~106s |
| Go | 39 | 100% (39/39) | 100% (39/39) | ~142s |
| JavaScript | 49 | 98% (48/49) | 100% (49/49) | ~196s |
| Java | 47 | TBD | TBD | TBD |
| Rust | 30 | TBD | TBD | TBD |
| C++ | 26 | TBD | TBD | TBD |

**Current total (122/225): 99.2% attempt 1, 100% attempt 2**

## Methodology

### Tool
- **GitHub Copilot CLI** v1.0.64 (`copilot --yolo -p "<prompt>"`)
- **Model**: Claude Opus 4.8 (configured via Copilot settings)

### How It Works

Unlike standard Aider leaderboard entries which use a single LLM call to generate/edit code, Copilot CLI operates as a **coding agent**:

1. The CLI receives the exercise directory containing instructions, starter code, and test files
2. It reads the problem description and existing code
3. It writes a solution
4. It can run tests and read results
5. It iterates until tests pass (all within a single "attempt")

This is fundamentally different from the single-prompt approach.

### 2-Attempt Protocol

Following the benchmark standard protocol:
- **Attempt 1**: Copilot CLI gets the exercise with all tests enabled
- **Attempt 2** (if attempt 1 fails): Test failure output (truncated to 3000 chars) is fed back as context for a retry

### Runner Script

The full benchmark runner is `run-benchmark.ps1` - a PowerShell script that orchestrates exercise discovery, prompt construction, Copilot CLI invocation, test execution, retry logic, and results collection.

## Raw Data

Each language has a results directory containing:
- `results.json` - structured results with per-exercise pass/fail, timing, and attempt data
- `run-{timestamp}.log` - full stdout log of the benchmark run
- `{exercise}-prompt.txt` - the exact prompt sent to Copilot CLI
- `{exercise}-retry-prompt.txt` - retry prompt (only for exercises that failed attempt 1)

## Comparison to Leaderboard

| Model | Pass Rate 1 | Pass Rate 2 |
|-------|-------------|-------------|
| **Copilot CLI (Opus 4.8)** | **99.2%** | **100%** |
| gpt-5 (high) | 52.0% | 88.0% |
| o3-pro (high) | 43.6% | 84.9% |
| gemini-2.5-pro (32k thinking) | 46.2% | 83.1% |
| claude-opus-4 (32k thinking) | 37.3% | 72.0% |

## Reproducing

```powershell
git clone https://github.com/tamirdresher/squad-polyglot-benchmark
cd squad-polyglot-benchmark
pwsh -File run-benchmark.ps1 -Language python -NoAgent
```

Requirements: GitHub Copilot CLI, Python 3.12+, Go 1.23+, Node.js 22+, Java 17+, Rust 1.96+, CMake + MSVC
