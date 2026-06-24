"""Test executor — runs unit tests for each language and captures output."""

import subprocess
from pathlib import Path


# Timeout for test execution (3 minutes, same as Aider)
TEST_TIMEOUT = 180

# Map file extensions to test commands
TEST_COMMANDS = {
    ".py": ["python", "-m", "pytest", "--tb=short", "-q"],
    ".rs": ["cargo", "test", "--", "--include-ignored"],
    ".go": ["go", "test", "./..."],
    ".js": ["/app/scripts/npm-test.sh"],
    ".cpp": ["/app/scripts/cpp-test.sh"],
    ".java": ["./gradlew", "test"],
}


def run_tests(testdir: Path, test_files: list[str]) -> tuple[bool, str]:
    """Run unit tests for an exercise and return (passed, error_output).

    Args:
        testdir: Path to the exercise directory.
        test_files: List of test file paths (relative to testdir).

    Returns:
        (True, "") if tests pass, (False, error_output) if they fail.

    Raises:
        subprocess.TimeoutExpired: If tests exceed timeout.
    """
    # Determine language from test file extensions
    extensions = {Path(f).suffix for f in test_files}

    command = None
    for ext in extensions:
        if ext in TEST_COMMANDS:
            command = TEST_COMMANDS[ext]
            break

    if command is None:
        return False, f"No test command found for extensions: {extensions}"

    # Enable all tests for JavaScript (Exercism uses xtest for skipped tests)
    if ".js" in extensions:
        for spec_file in testdir.glob("*.spec.js"):
            content = spec_file.read_text(encoding="utf-8", errors="replace")
            content = content.replace("xtest(", "test(")
            content = content.replace("xit(", "it(")
            content = content.replace("test.skip(", "test(")
            spec_file.write_text(content, encoding="utf-8")

    # Special handling per language
    if ".js" in extensions:
        # npm install first
        _run_cmd(["npm", "install", "--silent"], testdir, timeout=60)
    elif ".java" in extensions:
        # Make gradlew executable
        gradlew = testdir / "gradlew"
        if gradlew.exists():
            gradlew.chmod(0o755)

    try:
        result = subprocess.run(
            command,
            cwd=str(testdir),
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT,
        )

        if result.returncode == 0:
            return True, ""
        else:
            # Combine stdout and stderr for error context
            output = ""
            if result.stdout:
                output += result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            # Truncate very long output to avoid token waste
            if len(output) > 8000:
                output = output[:4000] + "\n\n... (truncated) ...\n\n" + output[-4000:]
            return False, output.strip()

    except subprocess.TimeoutExpired:
        raise
    except FileNotFoundError as e:
        return False, f"Test command not found: {e}"


def _run_cmd(cmd: list[str], cwd: Path, timeout: int = 60) -> None:
    """Run a helper command silently."""
    try:
        subprocess.run(cmd, cwd=str(cwd), capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
