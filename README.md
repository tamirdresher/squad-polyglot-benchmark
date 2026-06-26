# Squad Polyglot Benchmark Results

## 🏆 Final Score: 222/225 (98.7%)

Running the [Aider Polyglot Benchmark](https://aider.chat/docs/leaderboards/) using **Squad** — GitHub Copilot CLI's multi-agent orchestration system.

## Results Summary

| Language   | Exercises | Attempt 1       | Attempt 2       | Avg Time |
|------------|-----------|-----------------|-----------------|----------|
| Python     | 34        | 34/34 (100.0%)  | 34/34 (100.0%)  | 118s     |
| Go         | 39        | 39/39 (100.0%)  | 39/39 (100.0%)  | 261s     |
| JavaScript | 49        | 49/49 (100.0%)  | 49/49 (100.0%)  | 186s     |
| Java       | 47        | 46/47 (97.9%)   | 46/47 (97.9%)   | 221s     |
| Rust       | 30        | 30/30 (100.0%)  | 30/30 (100.0%)  | 110s     |
| C++        | 26        | 24/26 (92.3%)   | 24/26 (92.3%)   | 488s     |
| **Total**  | **225**   | **222/225 (98.7%)** | **222/225 (98.7%)** | **221s** |

### Failed Exercises (3)

| Language | Exercise    | Notes |
|----------|-------------|-------|
| Java     | `forth`     | Stack-based language interpreter — failed both attempts |
| C++      | `gigasecond`| Date/time calculation — compilation issues |
| C++      | `meetup`    | Date enumeration — compilation issues |

## Comparison with Leaderboard

| #  | Agent/Model                   | Pass Rate |
|----|-------------------------------|-----------|
| — | **Squad (Copilot CLI + Opus 4.8)** | **98.7%** |
| 1  | gpt-5 (high reasoning)        | 88.0%     |
| 2  | claude-sonnet-4-5 (whole)     | 79.6%     |
| 3  | o3 (diff)                     | 79.1%     |

## Methodology

### Tool Stack

- **GitHub Copilot CLI** v1.0.64
- **Agent**: Squad (`copilot --yolo --agent squad`)
- **Model**: Claude Opus 4.8 (configured via Copilot settings)
- **Platform**: Windows 11, run locally

### What is Squad?

Squad is a multi-agent orchestration system built on GitHub Copilot CLI. When invoked with `--agent squad`, it creates a team of AI agents that collaborate on coding tasks. For this benchmark, Squad operates as a coding agent that:

1. Reads the exercise directory (instructions, starter code, test files)
2. Writes a complete solution
3. Runs the test suite to verify correctness
4. If tests fail on attempt 1, reads error output and produces a revised solution (attempt 2)

### Benchmark Protocol

The Aider Polyglot Benchmark consists of 225 [Exercism](https://exercism.org/) coding problems across 6 languages. Each exercise gets 2 attempts:

- **Attempt 1**: Agent receives the problem description + starter code, produces a solution, tests are run
- **Attempt 2**: If attempt 1 fails, agent receives the test failure output and produces a revised solution

### Command Used

```powershell
.\run-benchmark.ps1 -Language <lang>
```

Which internally runs:

```powershell
copilot --yolo --agent squad -p "<exercise prompt with instructions>"
```

### Two-Attempt Protocol

The runner (`run-benchmark.ps1`) implements the benchmark protocol:

1. Copies fresh exercise source to a benchmark directory
2. Enables all unit tests (removes skips/disabled annotations)
3. Builds a prompt with the problem description + all source files
4. Runs `copilot --yolo --agent squad -p "<prompt>"`
5. Runs the language-specific test command
6. If tests fail: builds a retry prompt with failure output, runs copilot again, re-tests
7. Records pass/fail + timing for both attempts

## Reproducing These Results

### Prerequisites

- [GitHub Copilot CLI](https://docs.github.com/en/copilot/using-github-copilot/using-github-copilot-in-the-command-line) v1.0.64+
- Squad agent configured (`.github/agents/squad.agent.md` in your repo)
- Language toolchains: Python 3.12+, Go 1.23+, Node.js 22+, JDK 17+, Rust 1.75+, CMake 3.20+ with Ninja

### Steps

1. Clone this repo:
   ```bash
   git clone https://github.com/tamirdresher/squad-polyglot-benchmark.git
   cd squad-polyglot-benchmark
   ```

2. Install exercise sources (already included in `exercises/`):
   ```bash
   # Sources are pre-downloaded from Exercism track repos
   # If you need fresh copies:
   # git clone https://github.com/exercism/python exercises/python
   # git clone https://github.com/exercism/go exercises/go
   # etc.
   ```

3. Run a single language:
   ```powershell
   .\run-benchmark.ps1 -Language python
   ```

4. Run all languages:
   ```powershell
   foreach ($lang in @("python","go","javascript","java","rust","cpp")) {
       .\run-benchmark.ps1 -Language $lang
   }
   ```

### Runner Parameters

| Parameter      | Description                           | Default |
|----------------|---------------------------------------|---------|
| `-Language`    | Which language to run                 | Required |
| `-NoAgent`     | Skip Squad agent (bare copilot)       | $false  |
| `-MaxExercises`| Limit number of exercises             | All     |
| `-StartFrom`   | Start from exercise N (1-indexed)     | 1       |

### C++ Notes

C++ exercises use CMake + Ninja for building. On Windows, the runner uses `subst B:` to shorten paths (CMake has path length issues). The runner handles this automatically but requires Visual Studio 2022 build tools.

### Known Issues

- **Rust runner crash**: The runner occasionally crashes after ~16 exercises due to a process handle leak. Workaround: re-run with `-StartFrom 17`.
- **C++ subst drive**: Copilot CLI needs git context, so it runs from the real path while CMake builds use the B: subst drive.

## Repository Structure

```
├── run-benchmark.ps1          # Main benchmark runner script
├── results/
│   ├── python/results.json    # Per-exercise pass/fail + timing
│   ├── go/results.json
│   ├── javascript/results.json
│   ├── java/results.json
│   ├── rust/results.json
│   ├── cpp/results.json
│   └── */run-*.log            # Full timestamped execution logs
├── exercises/                  # Exercism exercise sources (per language)
├── .github/
│   └── agents/
│       └── squad.agent.md     # Squad agent definition
└── README.md
```

## Raw Data

All results are in `results/{language}/results.json`. Each file contains:

```json
{
  "language": "python",
  "total": 34,
  "pass_1": 34,
  "pass_2": 34,
  "rate_1": 100.0,
  "rate_2": 100.0,
  "exercises": [
    {
      "exercise": "beer-song",
      "pass_1": true,
      "pass_2": true,
      "time_1": 116.37,
      "time_2": 0
    }
  ]
}
```

Full execution logs (`run-*.log`) contain timestamped output showing exactly what copilot did for each exercise.

## Date

Benchmark run: June 25-26, 2026

## License

MIT
