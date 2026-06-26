"""pytest fixtures for loop-engineering tests."""

import pytest
import tempfile
import os


@pytest.fixture
def tmp_dir():
    """Temporary directory that auto-cleans up."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def tmp_tasks_md(tmp_dir):
    """Create a temporary tasks.md file and return its path."""
    path = os.path.join(tmp_dir, "tasks.md")
    return path
