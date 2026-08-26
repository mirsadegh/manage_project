"""
Tests for H3 (MIME override for legacy dangerous files) and H4
(defense-in-depth security headers on download/preview responses).
"""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
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
    return Project.objects.create(name='Hardening Project', owner=user)


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
    *, file_type, filename, body, is_safe=True, is_scanned=True,
):
    return Attachment.objects.create(
        content_type=project_ct,
        object_id=project.id,
        uploaded_by=user,
        original_filename=filename,
        file_size=len(body),
        file_type=file_type,
        file_hash='c' * 64,
        file=SimpleUploadedFile(filename, body, content_type=file_type),
        is_scanned=is_scanned,
        is_safe=is_safe,
    )


# ---------------------------------------------------------------------------
# H3: dangerous MIME override
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_legacy_dangerous_mime_served_as_octet_stream(
    auth_client, project, user, project_ct,
):
    """
    H3: pre-C3 attachments with dangerous MIMEs (e.g. image/svg+xml) are
    served with Content-Type: application/octet-stream so browsers cannot
    render them as their original type.
    """
    attachment = _create_attachment(
        project, user, project_ct,
        file_type='image/svg+xml',
        filename='legacy.svg',
        body=b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
    )
    url = reverse('attachment-download', kwargs={'pk': attachment.id})
    response = auth_client.get(url)
    assert response.status_code == 200, response.content
    assert response['Content-Type'] == 'application/octet-stream'


@pytest.mark.django_db
def test_safe_mime_served_with_original_type(
    auth_client, project, user, project_ct,
):
    """H3 regression guard: safe MIMEs pass through unchanged."""
    attachment = _create_attachment(
        project, user, project_ct,
        file_type='application/pdf',
        filename='doc.pdf',
        body=b'%PDF-1.4 body',
    )
    url = reverse('attachment-download', kwargs={'pk': attachment.id})
    response = auth_client.get(url)
    assert response.status_code == 200, response.content
    assert response['Content-Type'] == 'application/pdf'


# ---------------------------------------------------------------------------
# H4: defense-in-depth headers
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_download_response_has_security_headers(
    auth_client, project, user, project_ct,
):
    """H4: download responses carry CSP, nosniff, X-Frame-Options, Referrer-Policy."""
    attachment = _create_attachment(
        project, user, project_ct,
        file_type='application/pdf',
        filename='doc.pdf',
        body=b'%PDF-1.4 body',
    )
    url = reverse('attachment-download', kwargs={'pk': attachment.id})
    response = auth_client.get(url)
    assert response.status_code == 200

    csp = response['Content-Security-Policy']
    assert "default-src 'none'" in csp
    assert response['X-Content-Type-Options'] == 'nosniff'
    assert response['X-Frame-Options'] == 'DENY'
    assert response['Referrer-Policy'] == 'no-referrer'


@pytest.mark.django_db
def test_preview_response_has_security_headers(
    auth_client, project, user, project_ct,
):
    """H4: preview responses carry the same hardening headers."""
    # Minimal PNG so the Attachment.save() hook sets is_image=True and the
    # preview endpoint's type gate accepts it.
    png_bytes = (
        b'\x89PNG\r\n\x1a\n'
        b'\x00\x00\x00\rIHDR'
        b'\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
        b'\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa3\x9b\xfa\x99\x00'
        b'\x00\x00\x00IEND\xaeB`\x82'
    )
    attachment = _create_attachment(
        project, user, project_ct,
        file_type='image/png',
        filename='pixel.png',
        body=png_bytes,
    )
    # Sanity: Attachment.save() should have flagged it as an image.
    assert attachment.is_image is True

    url = reverse('attachment-preview', kwargs={'pk': attachment.id})
    response = auth_client.get(url)
    assert response.status_code == 200, response.content

    csp = response['Content-Security-Policy']
    assert "default-src 'none'" in csp
    assert response['X-Content-Type-Options'] == 'nosniff'
    assert response['X-Frame-Options'] == 'DENY'
    assert response['Referrer-Policy'] == 'no-referrer'
