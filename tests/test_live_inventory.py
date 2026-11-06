"""Deterministic deletion race, with strict final/archive checks retained."""
from contextlib import contextmanager

import pytest

from backend import execution


def vanish_during_scan(monkeypatch, root, *, error=None):
    original = execution.os.scandir

    @contextmanager
    def racing(path):
        with original(path) as scan:
            paths = [entry.path for entry in scan]
        # Windows DirEntry can cache stat during enumeration; exercise the Linux
        # fresh-stat failure explicitly on both platforms.
        class Entry:
            def __init__(self, value):
                self.path = value

            def stat(self, **kwargs):
                return execution.Path(self.path).stat(**kwargs)
        entries = [Entry(value) for value in paths]
        victim = root / 'eplusout.dbg'
        if victim.exists():
            victim.unlink()
        if error:
            class Fault:
                path = str(victim)

                def stat(self, **kwargs):
                    raise error
            entries = [Fault()]
        yield iter(entries)

    monkeypatch.setattr(execution.os, 'scandir', racing)


def test_live_deleted_debug_file_does_not_abort(monkeypatch, tmp_path):
    (tmp_path / 'eplusout.dbg').write_text('transient')
    (tmp_path / 'result').write_text('actual')
    vanish_during_scan(monkeypatch, tmp_path)
    files, size = execution.inventory(tmp_path, 100, 10, live=True)
    assert [(path.name, length) for path, length in files] == [('result', 6)]
    assert size == 6


def test_final_inventory_still_rejects_disappearance(monkeypatch, tmp_path):
    (tmp_path / 'eplusout.dbg').write_text('transient')
    vanish_during_scan(monkeypatch, tmp_path)
    with pytest.raises(FileNotFoundError):
        execution.inventory(tmp_path, 100, 10)


def test_live_permission_failure_not_suppressed(monkeypatch, tmp_path):
    (tmp_path / 'eplusout.dbg').write_text('transient')
    vanish_during_scan(monkeypatch, tmp_path, error=PermissionError('denied'))
    with pytest.raises(PermissionError):
        execution.inventory(tmp_path, 100, 10, live=True)


def test_live_budget_still_enforced_after_deletion(monkeypatch, tmp_path):
    (tmp_path / 'eplusout.dbg').write_text('transient')
    (tmp_path / 'result').write_bytes(b'x' * 101)
    vanish_during_scan(monkeypatch, tmp_path)
    with pytest.raises(execution.ExecutionError, match='budget'):
        execution.inventory(tmp_path, 100, 10, live=True)


def test_archive_never_uses_live_exception(monkeypatch, tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'eplusout.dbg').write_text('transient')
    vanish_during_scan(monkeypatch, source)
    with pytest.raises(FileNotFoundError):
        execution.archive_output(source, tmp_path / 'archive', execution.Policy())
