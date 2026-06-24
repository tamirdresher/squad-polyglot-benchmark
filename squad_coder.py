"""Squad Coder — Claude API integration for the Polyglot Benchmark.

Sends Exercism problems to Claude Opus 4.6 with a code-expert system prompt,
and returns the complete file content as whole-file edits.
"""

import os
import re
from pathlib import Path

from anthropic import Anthropic

SYSTEM_PROMPT = """\
You are a senior software engineer solving Exercism coding problems.
Your task is to implement the solution in the provided file(s).

Rules:
- Return ONLY the complete file content for each file that needs changes.
- Use the exact format shown below for each file.
- Do NOT change function/class names — they are referenced by unit tests.
- Use ONLY standard libraries. Do NOT suggest installing packages.
- Write clean, correct, complete implementations.
- If multiple files need edits, return each one in a separate block.

Output format — for EACH file you modify, return:

```path/to/filename.ext
<complete file content here>
```

Return NOTHING else — no explanations, no markdown outside the code blocks.
"""

RETRY_SYSTEM_PROMPT = """\
You are a senior software engineer fixing a failing implementation.
The previous attempt failed unit tests. You are given the test errors below.

Rules:
- The tests are CORRECT. Do NOT try to change them.
- Fix the code to make the tests pass.
- Return ONLY the complete file content using the same format.
- Use ONLY standard libraries.
- Preserve existing function/class names.

Output format — for EACH file you modify, return:

```path/to/filename.ext
<complete file content here>
```

Return NOTHING else — no explanations, no markdown outside the code blocks.
"""


class SquadCoder:
    """Sends coding tasks to Claude and parses whole-file responses."""

    def __init__(self, model: str = "claude-opus-4-20250514", max_tokens: int = 16384):
        self.client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.max_tokens = max_tokens
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0

    def solve(self, instructions: str, file_contents: dict[str, str]) -> dict[str, str]:
        """First attempt: solve the exercise from instructions.

        Args:
            instructions: The Exercism problem description.
            file_contents: Dict of {relative_path: current_content} for solution files.

        Returns:
            Dict of {relative_path: new_content} with the model's solution.
        """
        user_message = self._build_first_message(instructions, file_contents)
        response = self._call_api(SYSTEM_PROMPT, user_message)
        return self._parse_response(response, file_contents)

    def retry(self, test_errors: str, file_contents: dict[str, str]) -> dict[str, str]:
        """Second attempt: fix based on test errors.

        Args:
            test_errors: The test failure output.
            file_contents: Dict of {relative_path: current_content} for solution files.

        Returns:
            Dict of {relative_path: new_content} with the fixed solution.
        """
        user_message = self._build_retry_message(test_errors, file_contents)
        response = self._call_api(RETRY_SYSTEM_PROMPT, user_message)
        return self._parse_response(response, file_contents)

    def _build_first_message(self, instructions: str, file_contents: dict[str, str]) -> str:
        parts = [instructions, "\n\n---\n\nFiles to modify:\n"]
        for path, content in file_contents.items():
            parts.append(f"\n```{path}\n{content}\n```\n")
        file_list = ", ".join(file_contents.keys())
        parts.append(
            f"\nUse the above instructions to modify the supplied files: {file_list}\n"
            "Don't change the names of existing functions or classes, "
            "as they may be referenced from other code like unit tests, etc.\n"
            "Only use standard libraries, don't suggest installing any packages.\n"
        )
        return "".join(parts)

    def _build_retry_message(self, test_errors: str, file_contents: dict[str, str]) -> str:
        parts = ["The tests produced these errors:\n\n", test_errors, "\n\n---\n\nCurrent files:\n"]
        for path, content in file_contents.items():
            parts.append(f"\n```{path}\n{content}\n```\n")
        file_list = ", ".join(file_contents.keys())
        parts.append(
            f"\nThe tests are correct, don't try and change them.\n"
            f"Fix the code in {file_list} to resolve the errors.\n"
        )
        return "".join(parts)

    def _call_api(self, system: str, user_message: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        # Track token usage
        usage = response.usage
        self.total_input_tokens += usage.input_tokens
        self.total_output_tokens += usage.output_tokens
        # Approximate cost (Opus 4.6: $15/M input, $75/M output)
        cost = (usage.input_tokens * 15 + usage.output_tokens * 75) / 1_000_000
        self.total_cost += cost

        return response.content[0].text

    def _parse_response(self, response: str, file_contents: dict[str, str]) -> dict[str, str]:
        """Parse code blocks from response. Format: ```filename\ncontent\n```"""
        result = {}
        # Match fenced code blocks with a filename on the opening line
        pattern = r"```(\S+)\n(.*?)```"
        matches = re.findall(pattern, response, re.DOTALL)

        if matches:
            for filename, content in matches:
                # Strip language specifiers that might be appended
                # Normalize: the filename might be just the basename or a relative path
                clean_name = filename.strip()
                # Try to match against known file paths
                matched_path = self._match_filename(clean_name, file_contents.keys())
                if matched_path:
                    result[matched_path] = content.rstrip("\n") + "\n"
        
        # If no files matched via filename parsing, try to assign to the first/only file
        if not result and len(file_contents) == 1:
            # Try to extract any code block content
            code_blocks = re.findall(r"```(?:\w*)\n(.*?)```", response, re.DOTALL)
            if code_blocks:
                only_path = list(file_contents.keys())[0]
                result[only_path] = code_blocks[0].rstrip("\n") + "\n"

        # Fallback: if the response looks like raw code (no markdown), use it as-is
        if not result and len(file_contents) == 1 and "```" not in response:
            only_path = list(file_contents.keys())[0]
            result[only_path] = response.rstrip("\n") + "\n"

        return result

    def _match_filename(self, name: str, known_paths) -> str | None:
        """Match a filename from the response to a known solution file path."""
        known = list(known_paths)
        # Exact match
        if name in known:
            return name
        # Basename match
        for path in known:
            if Path(path).name == Path(name).name:
                return path
            # Also try matching without leading directory
            if path.endswith(name) or name.endswith(Path(path).name):
                return path
        # If only one file, return it
        if len(known) == 1:
            return known[0]
        return None
