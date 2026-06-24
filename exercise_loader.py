#!/usr/bin/env python3
"""Squad Polyglot Benchmark — Local Runner via Copilot CLI.

This script prepares exercises for dispatch through Copilot CLI's task tool.
It reads exercise data, generates prompts, and collects results.

Usage: This is invoked by the orchestrating Copilot session which dispatches
each exercise as a sub-agent task.
"""

import json
import os
import sys
from pathlib import Path


def load_exercise(testdir: Path) -> dict:
    """Load all exercise data needed to generate a prompt for the agent."""
    config_file = testdir / ".meta" / "config.json"
    if not config_file.exists():
        raise ValueError(f"No config file: {config_file}")

    config = json.loads(config_file.read_text(encoding="utf-8"))

    test_files = config.get("files", {}).get("test", [])
    solution_files = list(config.get("files", {}).get("solution", []))

    # Build instructions
    instructions = ""
    intro = testdir / ".docs" / "introduction.md"
    if intro.exists():
        instructions += intro.read_text(encoding="utf-8", errors="replace")
    inst_file = testdir / ".docs" / "instructions.md"
    if inst_file.exists():
        instructions += inst_file.read_text(encoding="utf-8", errors="replace")
    append_file = testdir / ".docs" / "instructions.append.md"
    if append_file.exists():
        instructions += append_file.read_text(encoding="utf-8", errors="replace")

    # Load solution file contents
    file_contents = {}
    for fpath in solution_files:
        full_path = testdir / fpath
        if full_path.exists():
            file_contents[fpath] = full_path.read_text(encoding="utf-8", errors="replace")

    # Determine language from directory structure
    # Pattern: exercises/{lang}/exercises/practice/{name}
    parts = str(testdir).replace("\\", "/").split("/")
    lang = "unknown"
    for i, p in enumerate(parts):
        if p == "exercises" and i + 2 < len(parts) and parts[i + 1] == "exercises":
            lang = parts[i - 1] if i > 0 else "unknown"
            break
    # Simpler: look for language dirs
    for candidate in ["python", "go", "javascript", "rust", "cpp", "java"]:
        if f"/{candidate}/" in str(testdir).replace("\\", "/"):
            lang = candidate
            break

    return {
        "name": testdir.name,
        "language": lang,
        "instructions": instructions,
        "solution_files": file_contents,
        "test_files": test_files,
        "testdir": str(testdir),
    }


def build_prompt(exercise: dict, attempt: int = 1, test_errors: str = "") -> str:
    """Build the prompt to send to the Squad agent."""
    if attempt == 1:
        prompt = (
            "You are solving an Exercism coding problem. "
            "Return ONLY the complete file content — no explanations, no markdown fences, no commentary.\n\n"
            f"## Problem\n\n{exercise['instructions']}\n\n"
        )
        for path, content in exercise["solution_files"].items():
            prompt += f"## File to implement: {path}\n\n```\n{content}\n```\n\n"
        file_list = ", ".join(exercise["solution_files"].keys())
        prompt += (
            f"Implement the solution in {file_list}.\n"
            "Don't change the names of existing functions or classes.\n"
            "Only use standard libraries, don't suggest installing any packages.\n"
            "Output ONLY the complete file content. No markdown fences. No explanations."
        )
    else:
        prompt = (
            "The previous implementation failed unit tests. Here are the errors:\n\n"
            f"```\n{test_errors}\n```\n\n"
            "Current file(s):\n\n"
        )
        for path, content in exercise["solution_files"].items():
            prompt += f"## {path}\n\n```\n{content}\n```\n\n"
        file_list = ", ".join(exercise["solution_files"].keys())
        prompt += (
            "The tests are correct. Don't try to change them.\n"
            f"Fix the code in {file_list} to resolve the errors.\n"
            "Output ONLY the complete fixed file content. No markdown fences. No explanations."
        )
    return prompt


def get_test_command(language: str) -> list[str]:
    """Get the test command for a language."""
    commands = {
        "python": ["python", "-m", "pytest", "--tb=short", "-q"],
        "go": ["go", "test", "./..."],
        "javascript": ["npx", "jest", "--no-coverage"],
        "rust": ["cargo", "test", "--", "--include-ignored"],
        "cpp": ["cmake", "--build", "build", "&&", "ctest", "--test-dir", "build", "--output-on-failure"],
        "java": ["./gradlew", "test"],
    }
    return commands.get(language, [])


if __name__ == "__main__":
    # Utility: load and print exercise data as JSON for the orchestrator
    if len(sys.argv) < 2:
        print("Usage: python exercise_loader.py <exercise_dir>")
        sys.exit(1)

    testdir = Path(sys.argv[1])
    exercise = load_exercise(testdir)
    prompt = build_prompt(exercise)
    print(json.dumps({"exercise": exercise, "prompt": prompt}, indent=2, ensure_ascii=False))
