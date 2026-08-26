"""
Tests for C1 (fail-closed scanner behavior).

VirusScanner.scan_file must return (False, ...) in every failure mode:
- clamd module is None (not installed)
- clamd daemon is unreachable (ConnectionError on ping)
- any other exception during scanning

And (True, ...) only when the daemon reports a clean scan.
"""
import pytest
from unittest.mock import MagicMock

from files.virus_scanner import VirusScanner


# ---------------------------------------------------------------------------
# C1: clamd not installed -> fail closed
# ---------------------------------------------------------------------------

def test_missing_clamd_returns_false(monkeypatch):
    """When the clamd module is None, scan_file returns (False, ...)."""
    import files.virus_scanner as scanner_module
    monkeypatch.setattr(scanner_module, 'clamd', None)

    is_safe, message = VirusScanner.scan_file('/tmp/whatever.bin')

    assert is_safe is False
    assert message  # non-empty failure message


# ---------------------------------------------------------------------------
# C1: daemon unreachable -> fail closed
# ---------------------------------------------------------------------------

def test_daemon_down_fails_closed(monkeypatch):
    """
    When clamd is installed but the daemon is down (ping raises
    ConnectionError), scan_file returns (False, ...).
    """
    import files.virus_scanner as scanner_module

    # Build a fake clamd module: ConnectionError is a real exception class,
    # and ClamdUnixSocket() raises it on construction (mirroring the daemon
    # being unreachable).
    fake_clamd = MagicMock()
    fake_clamd.ConnectionError = ConnectionError

    def _raise_on_ping():
        raise ConnectionError('daemon not running')

    fake_clamd.ClamdUnixSocket = _raise_on_ping
    monkeypatch.setattr(scanner_module, 'clamd', fake_clamd)

    is_safe, message = VirusScanner.scan_file('/tmp/whatever.bin')

    assert is_safe is False
    assert message


# ---------------------------------------------------------------------------
# C1: clean scan -> safe
# ---------------------------------------------------------------------------

def test_clean_file_returns_true(monkeypatch):
    """When the daemon reports a clean scan (scan returns None), result is (True, ...)."""
    import files.virus_scanner as scanner_module

    fake_client = MagicMock()
    fake_client.ping.return_value = True
    fake_client.scan.return_value = None  # clamd convention: None == clean

    fake_clamd = MagicMock()
    fake_clamd.ConnectionError = ConnectionError
    fake_clamd.ClamdUnixSocket.return_value = fake_client
    monkeypatch.setattr(scanner_module, 'clamd', fake_clamd)

    is_safe, message = VirusScanner.scan_file('/tmp/clean.bin')

    assert is_safe is True
    assert 'clean' in message.lower()


# ---------------------------------------------------------------------------
# C1: infected file -> unsafe
# ---------------------------------------------------------------------------

def test_infected_file_returns_false(monkeypatch):
    """When the daemon reports FOUND, scan_file returns (False, ...)."""
    import files.virus_scanner as scanner_module

    fake_client = MagicMock()
    fake_client.ping.return_value = True
    # clamd returns a mapping: {path: (status, virus_name)}
    fake_client.scan.return_value = {
        '/tmp/evil.bin': ('FOUND', 'Eicar-Test-Signature'),
    }

    fake_clamd = MagicMock()
    fake_clamd.ConnectionError = ConnectionError
    fake_clamd.ClamdUnixSocket.return_value = fake_client
    monkeypatch.setattr(scanner_module, 'clamd', fake_clamd)

    is_safe, message = VirusScanner.scan_file('/tmp/evil.bin')

    assert is_safe is False
    assert 'Eicar' in message
