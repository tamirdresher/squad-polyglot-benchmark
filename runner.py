#!/usr/bin/env python3
"""Squad Polyglot Benchmark Runner.

Runs all 225 Exercism exercises through Squad's Claude-based coder,
following the same 2-attempt protocol as the Aider benchmark.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from squad_coder import SquadCoder
from test_executor import run_tests


def get_exercise_dirs(base_dir: Path, languages: list[str] | None = None) -> list[Path]:
    """Get all exercise directories, optionally filtered by language."""
    lang_dirs = [d for d in base_dir.iterdir() if d.is_dir()]

    if languages:
        requested = {lang.strip().lower() for lang in languages}
        lang_dirs = [d for d in lang_dirs if d.name.lower() in requested]

    exercise_dirs = []
    for lang_dir in lang_dirs:
        practice_dir = lang_dir / "exercises" / "practice"
        if practice_dir.exists():
            exercise_dirs.extend(d for d in practice_dir.iterdir() if d.is_dir())

    return sorted(exercise_dirs)


def load_exercise(testdir: Path) -> tuple[str, dict[str, str], list[str]]:
    """Load exercise instructions and solution files.

    Returns:
        (instructions, solution_file_contents, test_files)
    """
    config_file = testdir / ".meta" / "config.json"
    if not config_file.exists():
        raise ValueError(f"No config file: {config_file}")

    config = json.loads(config_file.read_text())

    # Get file lists from config
    test_files = config.get("files", {}).get("test", [])
    solution_files = set(config.get("files", {}).get("solution", []))

    # Build instructions from .docs/
    instructions = ""
    intro = testdir / ".docs" / "introduction.md"
    if intro.exists():
        instructions += intro.read_text(encoding="utf-8", errors="replace")
    instructions_file = testdir / ".docs" / "instructions.md"
    if instructions_file.exists():
        instructions += instructions_file.read_text(encoding="utf-8", errors="replace")
    append_file = testdir / ".docs" / "instructions.append.md"
    if append_file.exists():
        instructions += append_file.read_text(encoding="utf-8", errors="replace")

    # Load solution file contents
    file_contents = {}
    for fpath in solution_files:
        full_path = testdir / fpath
        if full_path.exists():
            file_contents[fpath] = full_path.read_text(encoding="utf-8", errors="replace")

    return instructions, file_contents, test_files


def run_exercise(
    exercise_dir: Path,
    original_dir: Path,
    output_dir: Path,
    model: str,
    tries: int = 2,
    verbose: bool = False,
) -> dict:
    """Run a single exercise through the Squad coder.

    Args:
        exercise_dir: Path to the exercise in the working copy.
        original_dir: Path to the original (pristine) exercise for restoring files.
        output_dir: Where to write results.
        model: Claude model to use.
        tries: Number of attempts.
        verbose: Print detailed output.

    Returns:
        Results dict compatible with Aider's .aider.results.json format.
    """
    testdir = exercise_dir
    testcase = testdir.name

    # Check for existing results
    results_file = testdir / ".aider.results.json"
    if results_file.exists():
        try:
            existing = json.loads(results_file.read_text())
            if existing and "tests_outcomes" in existing:
                return existing
        except json.JSONDecodeError:
            pass

    # Restore original solution files
    try:
        instructions, file_contents, test_files = load_exercise(testdir)
    except Exception as e:
        error_result = {"testcase": testcase, "exception": str(e)}
        results_file.write_text(json.dumps(error_result, indent=2))
        return error_result

    # Restore files from original
    config = json.loads((testdir / ".meta" / "config.json").read_text())
    solution_files = config.get("files", {}).get("solution", [])
    for fpath in solution_files:
        orig = original_dir / fpath
        dest = testdir / fpath
        if orig.exists():
            os.makedirs(dest.parent, exist_ok=True)
            shutil.copy(orig, dest)

    # Reload after restore
    file_contents = {}
    for fpath in solution_files:
        full_path = testdir / fpath
        if full_path.exists():
            file_contents[fpath] = full_path.read_text()

    if not file_contents:
        error_result = {"testcase": testcase, "exception": "No solution files found"}
        results_file.write_text(json.dumps(error_result, indent=2))
        return error_result

    coder = SquadCoder(model=model)
    test_outcomes = []
    timeouts = 0
    duration = 0.0

    for attempt in range(tries):
        start = time.time()

        try:
            if attempt == 0:
                # First attempt: solve from instructions
                new_contents = coder.solve(instructions, file_contents)
            else:
                # Retry: fix based on test errors
                new_contents = coder.retry(test_errors, file_contents)
        except Exception as e:
            if verbose:
                traceback.print_exc()
            duration += time.time() - start
            test_outcomes.append(False)
            break

        duration += time.time() - start

        # Write solution files
        for fpath, content in new_contents.items():
            dest = testdir / fpath
            os.makedirs(dest.parent, exist_ok=True)
            dest.write_text(content)
            # Update in-memory copy
            file_contents[fpath] = content

        # Run tests
        try:
            passed, test_errors = run_tests(testdir, test_files)
        except subprocess.TimeoutExpired:
            test_errors = "Tests timed out!"
            timeouts += 1
            passed = False

        test_outcomes.append(passed)

        if passed:
            break

        if verbose:
            print(f"  [{testcase}] Attempt {attempt + 1} failed")

    results = {
        "testdir": str(testdir),
        "testcase": testcase,
        "model": model,
        "edit_format": "whole",
        "tests_outcomes": test_outcomes,
        "cost": coder.total_cost,
        "duration": duration,
        "test_timeouts": timeouts,
        "num_error_outputs": 0,
        "num_user_asks": 0,
        "num_exhausted_context_windows": 0,
        "num_malformed_responses": 0,
        "syntax_errors": 0,
        "indentation_errors": 0,
        "lazy_comments": 0,
        "prompt_tokens": coder.total_input_tokens,
        "completion_tokens": coder.total_output_tokens,
    }

    results_file.write_text(json.dumps(results, indent=2))
    return results


def summarize_results(results_list: list[dict], total_exercises: int) -> dict:
    """Summarize all results into leaderboard-compatible stats."""
    completed = [r for r in results_list if "tests_outcomes" in r]

    if not completed:
        return {}

    tries = max(len(r["tests_outcomes"]) for r in completed)
    passed = [0] * tries

    total_cost = 0.0
    total_duration = 0.0
    total_timeouts = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for r in completed:
        outcomes = r["tests_outcomes"]
        # If passed on attempt i, count as passed for all subsequent tries
        for i, outcome in enumerate(outcomes):
            if outcome:
                for j in range(i, tries):
                    passed[j] += 1
                break

        total_cost += r.get("cost", 0)
        total_duration += r.get("duration", 0)
        total_timeouts += r.get("test_timeouts", 0)
        total_prompt_tokens += r.get("prompt_tokens", 0)
        total_completion_tokens += r.get("completion_tokens", 0)

    summary = {
        "test_cases": len(completed),
        "total_tests": total_exercises,
    }

    for i in range(tries):
        rate = 100 * passed[i] / len(completed) if completed else 0
        summary[f"pass_rate_{i+1}"] = round(rate, 1)
        summary[f"pass_num_{i+1}"] = passed[i]

    summary.update({
        "total_cost": round(total_cost, 4),
        "seconds_per_case": round(total_duration / len(completed), 1) if completed else 0,
        "test_timeouts": total_timeouts,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
    })

    return summary


def main():
    parser = argparse.ArgumentParser(description="Squad Polyglot Benchmark Runner")
    parser.add_argument(
        "--exercises-dir", default="exercises",
        help="Path to polyglot-benchmark exercises directory"
    )
    parser.add_argument(
        "--output-dir", default="results",
        help="Directory to store results"
    )
    parser.add_argument(
        "--model", default="claude-opus-4-20250514",
        help="Claude model to use"
    )
    parser.add_argument(
        "--threads", type=int, default=1,
        help="Number of parallel threads"
    )
    parser.add_argument(
        "--tries", type=int, default=2,
        help="Number of attempts per exercise"
    )
    parser.add_argument(
        "--languages", type=str, default=None,
        help="Comma-separated list of languages to run (e.g., python,go)"
    )
    parser.add_argument(
        "--num-tests", type=int, default=-1,
        help="Limit number of tests to run (-1 for all)"
    )
    parser.add_argument(
        "--keywords", type=str, default=None,
        help="Only run exercises matching keywords (comma-separated)"
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--stats", action="store_true", help="Only show stats for existing results")

    args = parser.parse_args()

    exercises_dir = Path(args.exercises_dir)
    if not exercises_dir.exists():
        print(f"Error: exercises directory not found: {exercises_dir}")
        print("Clone it: git clone https://github.com/Aider-AI/polyglot-benchmark exercises")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # Get exercise list
    languages = args.languages.split(",") if args.languages else None
    exercise_dirs = get_exercise_dirs(exercises_dir, languages)

    if not exercise_dirs:
        print("No exercises found!")
        sys.exit(1)

    # Filter by keywords
    if args.keywords:
        keywords = args.keywords.split(",")
        exercise_dirs = [
            d for d in exercise_dirs
            if any(kw in d.name for kw in keywords)
        ]

    # Limit number
    if args.num_tests > 0:
        exercise_dirs = exercise_dirs[:args.num_tests]

    print(f"Found {len(exercise_dirs)} exercises to run")
    print(f"Model: {args.model}")
    print(f"Threads: {args.threads}")
    print(f"Tries: {args.tries}")
    print()

    # Create working copy directory
    now = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    run_name = f"{now}--squad-opus-4.6"
    workdir = output_dir / run_name

    if not workdir.exists():
        print(f"Copying exercises to {workdir}...")
        shutil.copytree(exercises_dir, workdir)
        print("Done.")

    # Re-discover exercises in workdir
    work_exercises = get_exercise_dirs(workdir, languages)
    if args.keywords:
        keywords = args.keywords.split(",")
        work_exercises = [d for d in work_exercises if any(kw in d.name for kw in keywords)]
    if args.num_tests > 0:
        work_exercises = work_exercises[:args.num_tests]

    # Stats-only mode
    if args.stats:
        all_results = []
        for ex_dir in work_exercises:
            rf = ex_dir / ".aider.results.json"
            if rf.exists():
                try:
                    all_results.append(json.loads(rf.read_text()))
                except json.JSONDecodeError:
                    pass
        summary = summarize_results(all_results, len(work_exercises))
        print(json.dumps(summary, indent=2))
        return

    # Run exercises
    all_results = []

    if args.threads == 1:
        for ex_dir in tqdm(work_exercises, desc="Running exercises"):
            # Find corresponding original dir
            rel = ex_dir.relative_to(workdir)
            original = exercises_dir / rel
            result = run_exercise(ex_dir, original, output_dir, args.model, args.tries, args.verbose)
            all_results.append(result)
    else:
        with ThreadPoolExecutor(max_workers=args.threads) as executor:
            futures = {}
            for ex_dir in work_exercises:
                rel = ex_dir.relative_to(workdir)
                original = exercises_dir / rel
                future = executor.submit(
                    run_exercise, ex_dir, original, output_dir,
                    args.model, args.tries, args.verbose
                )
                futures[future] = ex_dir

            for future in tqdm(as_completed(futures), total=len(futures), desc="Running exercises"):
                try:
                    result = future.result()
                    all_results.append(result)
                except Exception as e:
                    print(f"Error in {futures[future]}: {e}")
                    all_results.append({"exception": str(e)})

    # Print summary
    print("\n" + "=" * 60)
    summary = summarize_results(all_results, len(work_exercises))
    print(json.dumps(summary, indent=2))

    # Write summary
    summary_file = workdir / "summary.json"
    summary_file.write_text(json.dumps(summary, indent=2))
    print(f"\nResults saved to: {workdir}")
    print(f"Summary: {summary_file}")


if __name__ == "__main__":
    main()
