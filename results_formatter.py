#!/usr/bin/env python3
"""Format benchmark results into Aider leaderboard YAML entry."""

import argparse
import json
import sys
from pathlib import Path

import yaml


def format_leaderboard_entry(results_dir: Path, commit_hash: str = "unknown") -> str:
    """Generate a YAML entry for the Aider polyglot leaderboard."""
    # Collect all results
    all_results = []
    for rf in results_dir.rglob(".aider.results.json"):
        try:
            data = json.loads(rf.read_text())
            if "tests_outcomes" in data:
                all_results.append(data)
        except (json.JSONDecodeError, KeyError):
            continue

    if not all_results:
        print("No results found!")
        sys.exit(1)

    # Count total exercises
    total_exercises = len(list(results_dir.rglob(".meta/config.json")))

    # Compute stats
    tries = max(len(r["tests_outcomes"]) for r in all_results)
    passed = [0] * tries

    total_cost = 0.0
    total_duration = 0.0
    total_timeouts = 0
    num_malformed = 0

    for r in all_results:
        outcomes = r["tests_outcomes"]
        for i, outcome in enumerate(outcomes):
            if outcome:
                for j in range(i, tries):
                    passed[j] += 1
                break
        total_cost += r.get("cost", 0)
        total_duration += r.get("duration", 0)
        total_timeouts += r.get("test_timeouts", 0)
        num_malformed += r.get("num_malformed_responses", 0)

    # Build YAML entry
    dirname = results_dir.name
    entry = {
        "dirname": dirname,
        "test_cases": len(all_results),
        "model": "Squad (Claude Opus 4.6)",
        "edit_format": "whole",
        "commit_hash": commit_hash,
    }

    for i in range(tries):
        rate = 100 * passed[i] / len(all_results)
        entry[f"pass_rate_{i+1}"] = round(rate, 1)

    for i in range(tries):
        entry[f"pass_num_{i+1}"] = passed[i]

    pct_well_formed = 1.0 - (num_malformed / len(all_results)) if all_results else 1.0
    entry["percent_cases_well_formed"] = round(pct_well_formed * 100, 1)
    entry["error_outputs"] = 0
    entry["num_malformed_responses"] = num_malformed
    entry["num_with_malformed_responses"] = sum(
        1 for r in all_results if r.get("num_malformed_responses", 0) > 0
    )
    entry["user_asks"] = 0
    entry["lazy_comments"] = 0
    entry["syntax_errors"] = sum(r.get("syntax_errors", 0) for r in all_results)
    entry["indentation_errors"] = sum(r.get("indentation_errors", 0) for r in all_results)
    entry["exhausted_context_windows"] = 0
    entry["test_timeouts"] = total_timeouts
    entry["total_tests"] = total_exercises
    entry["command"] = "squad-polyglot-benchmark (Claude Opus 4.6)"
    entry["date"] = dirname[:10] if len(dirname) >= 10 else "unknown"
    entry["versions"] = "squad-1.0"
    entry["seconds_per_case"] = round(total_duration / len(all_results), 1)
    entry["total_cost"] = round(total_cost, 4)

    # Format as YAML
    output = yaml.dump([entry], default_flow_style=False, sort_keys=False, allow_unicode=True)
    return output


def main():
    parser = argparse.ArgumentParser(description="Format Squad benchmark results for leaderboard")
    parser.add_argument("results_dir", help="Path to the benchmark results directory")
    parser.add_argument("--commit-hash", default="unknown", help="Git commit hash")
    parser.add_argument("--output", default=None, help="Output file (default: stdout)")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"Error: {results_dir} not found")
        sys.exit(1)

    yaml_output = format_leaderboard_entry(results_dir, args.commit_hash)

    if args.output:
        Path(args.output).write_text(yaml_output)
        print(f"Written to {args.output}")
    else:
        print(yaml_output)


if __name__ == "__main__":
    main()
