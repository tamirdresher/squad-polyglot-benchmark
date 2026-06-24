#!/usr/bin/env python3
"""Squad Polyglot Benchmark — Copilot CLI Runner.

Runs Exercism exercises through the actual Copilot CLI with Squad agent,
testing the full Squad pipeline end-to-end.

Protocol:
1. Squad is initialized in the workspace (done once before running)
2. For each exercise:
   a. Copy exercise to a clean working directory
   b. Run: copilot --yolo --agent squad -p "<task prompt>" -C <exercise_dir>
   c. Run unit tests
   d. If tests fail, re-run copilot with test errors as prompt (attempt 2)
   e. Record pass/fail result
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Timeout for copilot CLI calls (5 minutes per exercise)
COPILOT_TIMEOUT = 300
# Timeout for test execution (3 minutes)
TEST_TIMEOUT = 180

# Test commands per language
TEST_COMMANDS = {
    "python": ["python", "-m", "pytest", "--tb=short", "-q"],
    "go": ["go", "test", "./..."],
    "javascript": ["npx", "jest", "--no-coverage"],
    "java": ["./gradlew", "test"],
    "rust": ["cargo", "test", "--", "--include-ignored"],
    "cpp": ["cmake", "--build", "build", "&&", "ctest", "--test-dir", "build"],
}


def load_exercise_config(exercise_dir: Path) -> dict:
    """Load exercise metadata from .meta/config.json."""
    config_file = exercise_dir / ".meta" / "config.json"
    if not config_file.exists():
        raise ValueError(f"No config file: {config_file}")
    return json.loads(config_file.read_text(encoding="utf-8"))


def get_instructions(exercise_dir: Path) -> str:
    """Read exercise instructions from .docs/."""
    instructions = ""
    for fname in ["introduction.md", "instructions.md", "instructions.append.md"]:
        fpath = exercise_dir / ".docs" / fname
        if fpath.exists():
            instructions += fpath.read_text(encoding="utf-8", errors="replace")
    return instructions


def build_solve_prompt(exercise_dir: Path, config: dict) -> str:
    """Build the prompt for the first attempt."""
    instructions = get_instructions(exercise_dir)
    solution_files = config.get("files", {}).get("solution", [])

    file_contents = ""
    for fpath in solution_files:
        full = exercise_dir / fpath
        if full.exists():
            content = full.read_text(encoding="utf-8", errors="replace")
            file_contents += f"\n\nFile to implement ({fpath}):\n{content}\n"

    file_list = ", ".join(solution_files)
    return (
        f"Implement the solution for this Exercism exercise.\n\n"
        f"Instructions:\n{instructions}\n"
        f"{file_contents}\n"
        f"Edit {file_list} to implement the solution. "
        f"Don't change function/class names. Use only standard libraries. "
        f"Write the complete implementation."
    )


def build_retry_prompt(test_errors: str, config: dict, exercise_dir: Path) -> str:
    """Build the prompt for the retry attempt with test errors."""
    solution_files = config.get("files", {}).get("solution", [])
    file_list = ", ".join(solution_files)
    return (
        f"The previous implementation failed unit tests. Here are the errors:\n\n"
        f"{test_errors}\n\n"
        f"The tests are correct — don't try to change them. "
        f"Fix the code in {file_list} to resolve the errors."
    )


def enable_all_tests(exercise_dir: Path):
    """Enable skipped tests (xtest→test for JS, etc.)."""
    for spec in exercise_dir.glob("*.spec.js"):
        content = spec.read_text(encoding="utf-8", errors="replace")
        content = re.sub(r"\bxtest\(", "test(", content)
        content = re.sub(r"\bxit\(", "it(", content)
        content = content.replace("test.skip(", "test(")
        spec.write_text(content, encoding="utf-8")


def run_copilot(prompt: str, working_dir: Path, timeout: int = COPILOT_TIMEOUT) -> tuple[int, str]:
    """Run copilot CLI with the given prompt.

    Returns (exit_code, output).
    """
    cmd = [
        "copilot",
        "--yolo",
        "--agent", "squad",
        "-p", prompt,
        "-C", str(working_dir),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout + "\n" + result.stderr
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return -1, "Copilot CLI timed out"
    except FileNotFoundError:
        return -2, "copilot CLI not found"


def run_tests(exercise_dir: Path, language: str, test_files: list[str]) -> tuple[bool, str]:
    """Run unit tests and return (passed, error_output)."""
    command = TEST_COMMANDS.get(language)
    if not command:
        return False, f"No test command for language: {language}"

    # Pre-test setup
    if language == "javascript":
        enable_all_tests(exercise_dir)
        subprocess.run(["npm", "install", "--silent"], cwd=str(exercise_dir),
                      capture_output=True, timeout=60)
    elif language == "java":
        gradlew = exercise_dir / "gradlew"
        if gradlew.exists():
            gradlew.chmod(0o755)

    try:
        result = subprocess.run(
            command,
            cwd=str(exercise_dir),
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return True, ""
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        if len(output) > 6000:
            output = output[:3000] + "\n...(truncated)...\n" + output[-3000:]
        return False, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Tests timed out!"
    except FileNotFoundError as e:
        return False, f"Test command not found: {e}"


def detect_language(exercise_path: Path) -> str:
    """Detect language from exercise path."""
    path_str = str(exercise_path).replace("\\", "/")
    for lang in ["python", "go", "javascript", "rust", "cpp", "java"]:
        if f"/{lang}/" in path_str:
            return lang
    return "unknown"


def run_exercise(exercise_dir: Path, original_dir: Path, tries: int = 2, verbose: bool = False) -> dict:
    """Run a single exercise through Copilot CLI + Squad.

    Args:
        exercise_dir: Working copy of the exercise.
        original_dir: Pristine copy for file restoration.
        tries: Number of attempts.
        verbose: Print details.

    Returns:
        Result dict compatible with Aider's format.
    """
    testcase = exercise_dir.name
    language = detect_language(exercise_dir)

    # Check for existing result
    results_file = exercise_dir / ".squad-results.json"
    if results_file.exists():
        try:
            existing = json.loads(results_file.read_text())
            if existing.get("tests_outcomes"):
                if verbose:
                    print(f"  [{testcase}] Already completed, skipping")
                return existing
        except json.JSONDecodeError:
            pass

    # Load config
    try:
        config = load_exercise_config(exercise_dir)
    except Exception as e:
        return {"testcase": testcase, "language": language, "exception": str(e)}

    test_files = config.get("files", {}).get("test", [])
    solution_files = config.get("files", {}).get("solution", [])

    # Restore original files
    for fpath in solution_files:
        orig = original_dir / fpath
        dest = exercise_dir / fpath
        if orig.exists():
            os.makedirs(dest.parent, exist_ok=True)
            shutil.copy(orig, dest)

    test_outcomes = []
    duration = 0.0
    timeouts = 0
    copilot_output = ""

    for attempt in range(tries):
        start = time.time()

        if attempt == 0:
            prompt = build_solve_prompt(exercise_dir, config)
        else:
            prompt = build_retry_prompt(test_errors, config, exercise_dir)

        if verbose:
            print(f"  [{testcase}] Attempt {attempt + 1}...")

        exit_code, copilot_output = run_copilot(prompt, exercise_dir)
        duration += time.time() - start

        if exit_code == -1:
            timeouts += 1
            test_outcomes.append(False)
            break

        # Run tests
        passed, test_errors = run_tests(exercise_dir, language, test_files)
        test_outcomes.append(passed)

        if passed:
            if verbose:
                print(f"  [{testcase}] PASSED on attempt {attempt + 1}")
            break
        elif verbose:
            print(f"  [{testcase}] FAILED attempt {attempt + 1}")

    results = {
        "testcase": testcase,
        "language": language,
        "model": "Squad (Copilot CLI + Claude Opus 4.6)",
        "edit_format": "whole",
        "tests_outcomes": test_outcomes,
        "duration": round(duration, 1),
        "test_timeouts": timeouts,
    }

    results_file.write_text(json.dumps(results, indent=2))
    return results


def get_all_exercises(exercises_dir: Path, languages: list[str] | None = None) -> list[Path]:
    """Get all exercise directories."""
    lang_dirs = [d for d in exercises_dir.iterdir() if d.is_dir()]
    if languages:
        requested = {l.strip().lower() for l in languages}
        lang_dirs = [d for d in lang_dirs if d.name.lower() in requested]

    exercises = []
    for lang_dir in lang_dirs:
        practice = lang_dir / "exercises" / "practice"
        if practice.exists():
            exercises.extend(sorted(d for d in practice.iterdir() if d.is_dir()))
    return exercises


def main():
    parser = argparse.ArgumentParser(description="Squad Polyglot Benchmark via Copilot CLI")
    parser.add_argument("--exercises-dir", default="exercises", help="Polyglot-benchmark dir")
    parser.add_argument("--output-dir", default="results", help="Results output directory")
    parser.add_argument("--languages", type=str, default=None, help="Comma-sep languages")
    parser.add_argument("--tries", type=int, default=2, help="Attempts per exercise")
    parser.add_argument("--num-tests", type=int, default=-1, help="Limit exercises (-1=all)")
    parser.add_argument("--keywords", type=str, default=None, help="Filter exercises by name")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--stats", action="store_true", help="Show stats only")
    args = parser.parse_args()

    exercises_dir = Path(args.exercises_dir)
    if not exercises_dir.exists():
        print(f"Error: {exercises_dir} not found")
        print("Clone: git clone https://github.com/Aider-AI/polyglot-benchmark exercises")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Get exercises
    languages = args.languages.split(",") if args.languages else None
    exercises = get_all_exercises(exercises_dir, languages)

    if args.keywords:
        keywords = args.keywords.split(",")
        exercises = [e for e in exercises if any(kw in e.name for kw in keywords)]

    if args.num_tests > 0:
        exercises = exercises[:args.num_tests]

    print(f"Exercises: {len(exercises)}")
    print(f"Languages: {', '.join(set(detect_language(e) for e in exercises))}")
    print(f"Tries: {args.tries}")
    print()

    # Create working copy
    now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    workdir = output_dir / f"{now}--squad-copilot-cli"

    if not workdir.exists():
        print(f"Copying exercises to {workdir}...")
        shutil.copytree(exercises_dir, workdir)

    # Re-discover exercises in working copy
    work_exercises = get_all_exercises(workdir, languages)
    if args.keywords:
        work_exercises = [e for e in work_exercises if any(kw in e.name for kw in keywords)]
    if args.num_tests > 0:
        work_exercises = work_exercises[:args.num_tests]

    if args.stats:
        all_results = []
        for ex in work_exercises:
            rf = ex / ".squad-results.json"
            if rf.exists():
                try:
                    all_results.append(json.loads(rf.read_text()))
                except json.JSONDecodeError:
                    pass
        _print_summary(all_results, len(work_exercises))
        return

    # Run all exercises
    all_results = []
    for i, work_ex in enumerate(work_exercises, 1):
        rel = work_ex.relative_to(workdir)
        original = exercises_dir / rel
        lang = detect_language(work_ex)

        print(f"[{i}/{len(work_exercises)}] {lang}/{work_ex.name}")
        result = run_exercise(work_ex, original, args.tries, args.verbose)
        all_results.append(result)

        # Print running tally
        completed = [r for r in all_results if "tests_outcomes" in r]
        passed = sum(1 for r in completed if r["tests_outcomes"] and r["tests_outcomes"][-1])
        print(f"  Running: {passed}/{len(completed)} passed ({100*passed/len(completed):.0f}%)")

    print("\n" + "=" * 60)
    _print_summary(all_results, len(work_exercises))

    # Save summary
    summary_file = workdir / "summary.json"
    summary_file.write_text(json.dumps(all_results, indent=2))
    print(f"\nResults saved to: {workdir}")


def _print_summary(results: list[dict], total: int):
    """Print a summary of results."""
    completed = [r for r in results if "tests_outcomes" in r]
    if not completed:
        print("No results yet.")
        return

    passed_1 = sum(1 for r in completed if r["tests_outcomes"] and r["tests_outcomes"][0])
    passed_2 = sum(1 for r in completed if r["tests_outcomes"] and any(r["tests_outcomes"]))

    print(f"Completed: {len(completed)}/{total}")
    print(f"Pass rate (attempt 1): {100*passed_1/len(completed):.1f}% ({passed_1}/{len(completed)})")
    print(f"Pass rate (attempt 2): {100*passed_2/len(completed):.1f}% ({passed_2}/{len(completed)})")

    # Per-language breakdown
    by_lang = {}
    for r in completed:
        lang = r.get("language", "unknown")
        if lang not in by_lang:
            by_lang[lang] = {"total": 0, "passed": 0}
        by_lang[lang]["total"] += 1
        if r["tests_outcomes"] and any(r["tests_outcomes"]):
            by_lang[lang]["passed"] += 1

    print("\nPer language:")
    for lang, stats in sorted(by_lang.items()):
        rate = 100 * stats["passed"] / stats["total"] if stats["total"] else 0
        print(f"  {lang}: {stats['passed']}/{stats['total']} ({rate:.0f}%)")


if __name__ == "__main__":
    main()
