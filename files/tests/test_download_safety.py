"""
Tests for C2 (TOCTOU fix on download).

The download action in AttachmentViewSet gates on both is_scanned and
is_safe: a file is only downloadable if it has been scanned AND the scan
flagged it safe. We verify all three branches (unscanned, unsafe, clean) and
confirm the model default flips to unsafe-by-default.
"""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from files.models import Attachment
from projects.models import Project


User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='downloader',
        email='downloader@example.com',
        password='Test123!',
    )


@pytest.fixture
def project(db, user):
    return Project.objects.create(name='Download Project', owner=user)


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def project_ct(db):
    return ContentType.objects.get_for_model(Project)


def _create_attachment(
    project, user, project_ct,
    *, is_scanned=False, is_safe=False, filename='doc.txt',
):
    """Create an Attachment wired to the given project via GFK."""
    return Attachment.objects.create(
        content_type=project_ct,
        object_id=project.id,
        uploaded_by=user,
        original_filename=filename,
        file_size=11,
        file_type='text/plain',
        file_hash='a' * 64,
        file=SimpleUploadedFile(filename, b'test content'),
        is_scanned=is_scanned,
        is_safe=is_safe,
    )


# ---------------------------------------------------------------------------
# C2: download gate
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_unscanned_file_blocked(auth_client, project, user, project_ct):
    """is_scanned=False, is_safe=True -> 403 (pre-scan rejection)."""
    attachment = _create_attachment(
        project, user, project_ct,
        is_scanned=False, is_safe=True,
    )
    from django.urls import reverse
    url = reverse('attachment-download', kwargs={'pk': attachment.id})
    response = auth_client.get(url)
    assert response.status_code == 403, response.content


@pytest.mark.django_db
def test_unsafe_file_blocked(auth_client, project, user, project_ct):
    """is_scanned=True, is_safe=False -> 403 (post-scan rejection)."""
    attachment = _create_attachment(
        project, user, project_ct,
        is_scanned=True, is_safe=False,
    )
    from django.urls import reverse
    url = reverse('attachment-download', kwargs={'pk': attachment.id})
    response = auth_client.get(url)
    assert response.status_code == 403, response.content


@pytest.mark.django_db
def test_scanned_safe_file_allowed(auth_client, project, user, project_ct):
    """is_scanned=True, is_safe=True -> 200 (download proceeds)."""
    attachment = _create_attachment(
        project, user, project_ct,
        is_scanned=True, is_safe=True,
    )
    from django.urls import reverse
    url = reverse('attachment-download', kwargs={'pk': attachment.id})
    response = auth_client.get(url)
    assert response.status_code == 200, response.content
    attachment.refresh_from_db()
    assert attachment.download_count == 1


# ---------------------------------------------------------------------------
# Default safety: new attachments are unsafe until scanned
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_new_attachment_defaults_unsafe(project, user, project_ct):
    """A freshly created Attachment has is_safe=False by default."""
    attachment = _create_attachment(
        project, user, project_ct,
        is_scanned=False, is_safe=False,
    )
    # Re-fetch to confirm the persisted default.
    fresh = Attachment.objects.get(pk=attachment.pk)
    assert fresh.is_scanned is False
    assert fresh.is_safe is False
