"""Pure metadata exporter for file references in Markdown format.

Harness contribution: e0fced29-60e7-4f3c-9c13-170fe09fe1ac.
Adopted after independent remote and local contract tests.
"""

import json


def _longest_consecutive_backtick_run(text: str) -> int:
    """Return the length of the longest consecutive backtick sequence in text."""
    max_run = 0
    current_run = 0
    for ch in text:
        if ch == '`':
            current_run += 1
            if current_run > max_run:
                max_run = current_run
        else:
            current_run = 0
    return max_run


def export_references(assets):
    """Accept a list of dicts; return a Markdown document with a JSON fenced block.

    Raises ValueError when *assets* is not a list of dicts.
    """
    if not isinstance(assets, list):
        raise ValueError('assets must be a list')
    for item in assets:
        if not isinstance(item, dict):
            raise ValueError('each asset must be a dict')

    if not assets:
        return '# File references\n\nNo references registered.\n'

    json_text = json.dumps(assets, ensure_ascii=False, indent=2, sort_keys=True)
    longest_run = _longest_consecutive_backtick_run(json_text)
    fence_len = max(longest_run + 1, 3)
    fence = '`' * fence_len

    return f'# File references\n\n{fence}json\n{json_text}\n{fence}\n'
