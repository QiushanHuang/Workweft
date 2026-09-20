"""Harness contribution 6dfe279e-0599-4c58-a09f-0cfd43410ce8; import summary."""

_REQUIRED_KEYS = frozenset({'projects', 'tasks', 'assets'})


def _validate(preview):
    """Validate preview dict and return (projects, tasks, assets)."""
    if not isinstance(preview, dict):
        raise ValueError('preview must be a dict')
    if set(preview.keys()) != _REQUIRED_KEYS:
        raise ValueError('preview must contain exactly projects, tasks, assets')
    for k in ('projects', 'tasks', 'assets'):
        v = preview[k]
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError(f'{k} must be a non-negative integer, not {type(v).__name__}')
        if v < 0:
            raise ValueError(f'{k} must be non-negative, got {v}')
    return preview['projects'], preview['tasks'], preview['assets']


def summarize_import(preview):
    """Return a human-readable import summary string."""
    p, t, a = _validate(preview)
    return (
        f'{p} projects · {t} tasks · {a} references\n'
        'Import creates new copies; existing data is not overwritten. '
        'Tasks reset to todo.'
    )
