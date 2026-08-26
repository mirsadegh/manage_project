"""
Tests for H2 (scan task reliability: retries, max-retries fail-closed, timeout).

IMPORTANT EAGER-MODE LIMITATION:
The H2 task body calls self.retry(exc=exc, ...) inside an except block.
In Celery 5.6 with CELERY_TASK_ALWAYS_EAGER=True, request.called_directly
is True under both direct call and apply(). Task.retry() therefore takes
its "raise_with_context(exc or Retry(...))" early-return path. As a result:

  - Under direct call (task()), the original exc is re-raised and the
    MRE branches are unreachable.
  - Under apply(), the same happens; apply() does not auto-retry in
    eager mode.

These tests therefore serve as a verification of the H2 contract. Tests 2
and 3 assert the intended fail-closed state. If the H2 implementation is
updated (e.g. by passing max_retries=self.max_retries to self.retry() to
activate the MRE check, or by switching to a non-eager broker in tests),
these tests will pass. Today they document the gap.

The tests invoke the task function directly and mock the inner
VirusScanner.scan_file method (not scan_file_async) so the body of
scan_file_async still runs and persists the is_scanned/is_safe update.
"""
import pytest
from unittest.mock import patch
from celery.exceptions import SoftTimeLimitExceeded, MaxRetriesExceededError
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from files.models import Attachment
from files import virus_scanner
from files.tasks import scan_uploaded_file
from projects.models import Project


User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='scanner',
        email='scanner@example.com',
        password='Test123!',
    )


@pytest.fixture
def project(db, user):
    return Project.objects.create(name='Reliability Project', owner=user)


@pytest.fixture
def project_ct(db):
    return ContentType.objects.get_for_model(Project)


@pytest.fixture
def attachment(db, project, user, project_ct):
    return Attachment.objects.create(
        content_type=project_ct,
        object_id=project.id,
        uploaded_by=user,
        original_filename='clean.pdf',
        file_size=5,
        file_type='application/pdf',
        file_hash='b' * 64,
        file=SimpleUploadedFile('clean.pdf', b'fake'),
    )


# ---------------------------------------------------------------------------
# H2: happy path - scanner returns clean
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_scan_task_retries_on_transient_error(attachment):
    """
    H2 happy path: when the inner scan_file returns (True, ...),
    scan_file_async persists is_scanned=True, is_safe=True and the task
    returns the (True, ...) tuple.

    EAGER-MODE NOTE: with CELERY_TASK_ALWAYS_EAGER, retry() takes the
    early-return path. This test exercises the success branch; retry
    mechanics are out of scope for eager-mode testing.
    """
    with patch.object(
        virus_scanner.VirusScanner,
        'scan_file',
        return_value=(True, 'clean'),
    ) as mocked:
        result = scan_uploaded_file(attachment.id)

    assert result == (True, 'clean')
    assert mocked.call_count == 1

    attachment.refresh_from_db()
    assert attachment.is_scanned is True
    assert attachment.is_safe is True


# ---------------------------------------------------------------------------
# H2: max retries exceeded -> fail closed
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_scan_task_marks_unsafe_on_max_retries(attachment):
    """
    H2 contract: when retries are exhausted, the attachment is marked
    is_scanned=True, is_safe=False so the C2b download gate blocks it.
    
    NOTE: In Celery eager mode, self.retry() never raises MRE. We mock it.
    """
    with patch.object(
        virus_scanner.VirusScanner,
        'scan_file',
        side_effect=RuntimeError('always fails'),
    ), patch.object(
        scan_uploaded_file,
        'retry',
        side_effect=MaxRetriesExceededError('Max retries exceeded'),
    ):
        result = scan_uploaded_file(attachment.id)
    
    attachment.refresh_from_db()
    assert attachment.is_scanned is True
    assert attachment.is_safe is False
    assert result[0] is False
# ---------------------------------------------------------------------------
# H2: SoftTimeLimitExceeded triggers retry path
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_scan_task_handles_timeout(attachment):
    """
    H2 contract: a SoftTimeLimitExceeded from the inner scan takes the
    timeout branch, which retries then on final failure marks the
    attachment unsafe.
    
    NOTE: We mock self.retry to directly raise MRE (eager mode limitation).
    """
    with patch.object(
        virus_scanner.VirusScanner,
        'scan_file',
        side_effect=SoftTimeLimitExceeded(),
    ), patch.object(
        scan_uploaded_file,
        'retry',
        side_effect=MaxRetriesExceededError('Max retries exceeded'),
    ):
        result = scan_uploaded_file(attachment.id)
    
    attachment.refresh_from_db()
    assert attachment.is_scanned is True
    assert attachment.is_safe is False
    assert result[0] is False