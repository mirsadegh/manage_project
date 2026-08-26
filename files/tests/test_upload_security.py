"""
Tests for C1 (fail-closed scanner) and C3 (dangerous types blocked).

C3 removes 'image/svg+xml', 'text/html', 'application/javascript', and
'application/xml' (and their extensions) from the allowed types/extensions
lists. The MIME-based rejection is enforced by Attachment.clean() (called via
full_clean); the extension-based rejection is enforced by
FileExtensionValidator on the file field. Because the upload view does not
invoke full_clean, the extension validator is the active upload-time gate.

C1 makes VirusScanner.scan_file fail closed when clamd is missing. The
upload view schedules the scan via a Celery task (eager in tests); when
clamd is unavailable, the post-upload scan marks the attachment unsafe.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from files.models import Attachment
from projects.models import Project


User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures (self-contained; no shared conftest)
# ---------------------------------------------------------------------------

@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='uploader',
        email='uploader@example.com',
        password='Test123!',
    )


@pytest.fixture
def project(db, user):
    return Project.objects.create(
        name='Security Project',
        owner=user,
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def upload_url():
    from django.urls import reverse
    return reverse('attachment-list')


def _upload(client, url, project, name, body, content_type='application/octet-stream'):
    """Helper: POST a file to the attachment-list endpoint."""
    test_file = SimpleUploadedFile(name, body, content_type=content_type)
    return client.post(
        url,
        data={
            'file': test_file,
            'description': 'security test',
            'content_type': 'project',
            'object_id': project.id,
        },
        format='multipart',
    )


# ---------------------------------------------------------------------------
# C3: dangerous types blocked at upload
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_svg_upload_rejected(auth_client, upload_url, project):
    """SVG uploads are rejected by FileExtensionValidator (svg not in list)."""
    response = _upload(
        auth_client, upload_url, project,
        'evil.svg', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        content_type='image/svg+xml',
    )
    assert response.status_code == 400, response.content
    assert Attachment.objects.count() == 0


@pytest.mark.django_db
def test_html_upload_rejected(auth_client, upload_url, project):
    """HTML uploads are rejected by FileExtensionValidator (html not in list)."""
    response = _upload(
        auth_client, upload_url, project,
        'page.html', b'<html><body>x</body></html>',
        content_type='text/html',
    )
    assert response.status_code == 400, response.content
    assert Attachment.objects.count() == 0


@pytest.mark.django_db
def test_js_upload_rejected(auth_client, upload_url, project):
    """JS uploads are rejected by FileExtensionValidator (js not in list)."""
    response = _upload(
        auth_client, upload_url, project,
        'evil.js', b'function f(){return 1;}',
        content_type='application/javascript',
    )
    assert response.status_code == 400, response.content
    assert Attachment.objects.count() == 0


@pytest.mark.django_db
def test_xml_upload_rejected(auth_client, upload_url, project):
    """XML uploads are rejected by FileExtensionValidator (xml not in list)."""
    response = _upload(
        auth_client, upload_url, project,
        'data.xml', b'<?xml version="1.0"?><root/>',
        content_type='application/xml',
    )
    assert response.status_code == 400, response.content
    assert Attachment.objects.count() == 0


# ---------------------------------------------------------------------------
# Regression guards: allowed types still work
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_pdf_upload_allowed(auth_client, upload_url, project):
    """PDF uploads still succeed (regression guard for C3)."""
    response = _upload(
        auth_client, upload_url, project,
        'doc.pdf', b'%PDF-1.4 fake content',
        content_type='application/pdf',
    )
    assert response.status_code == 201, response.content
    assert Attachment.objects.count() == 1


@pytest.mark.django_db
def test_png_upload_allowed(auth_client, upload_url, project):
    """PNG uploads still succeed (regression guard for C3)."""
    # Minimal PNG header bytes
    png_bytes = (
        b'\x89PNG\r\n\x1a\n'
        b'\x00\x00\x00\rIHDR'
        b'\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89'
        b'\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa3\x9b\xfa\x99\x00'
        b'\x00\x00\x00IEND\xaeB`\x82'
    )
    response = _upload(
        auth_client, upload_url, project,
        'pixel.png', png_bytes,
        content_type='image/png',
    )
    assert response.status_code == 201, response.content
    assert Attachment.objects.count() == 1


# ---------------------------------------------------------------------------
# C1: fail-closed when clamd is missing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_missing_clamd_rejects_upload(auth_client, upload_url, project, monkeypatch):
    """
    When clamd is missing, VirusScanner.scan_file_async fails closed and the
    uploaded attachment is marked unsafe.

    NOTE: The upload endpoint does NOT call the scanner synchronously, so the
    HTTP response is still 201. The fail-closed behavior is observable on the
    resulting Attachment (is_safe=False). The Celery task runs eagerly in
    tests (CELERY_TASK_ALWAYS_EAGER=True), so the post-upload scan executes
    inline. We assert the post-upload state, which is the contract C1
    enforces.
    """
    import files.virus_scanner as scanner_module
    monkeypatch.setattr(scanner_module, 'clamd', None)

    response = _upload(
        auth_client, upload_url, project,
        'clean.pdf', b'%PDF-1.4 still clean bytes',
        content_type='application/pdf',
    )
    # Debug: print response for diagnosis
    print(f"\n=== DEBUG test_missing_clamd ===")
    print(f"Status: {response.status_code}")
    print(f"Data: {getattr(response, 'data', 'N/A')}")
    print(f"Content: {response.content[:500] if hasattr(response, 'content') else 'N/A'}")
    print(f"Attachment count: {Attachment.objects.count()}")
    print(f"=== END DEBUG ===\n")
    
    # Upload itself succeeds; the fail-closed gate is the post-upload scan.
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.content}"

    # گرفتن آخرین attachment بدون فیلتر (چون فقط یک attachment در این تست ساخته می‌شود)
    attachment = Attachment.objects.order_by('-id').first()
    assert attachment is not None, "At least one attachment should exist"
    
    # Fail-closed: the scan ran, found no scanner, and marked the file unsafe.
    assert attachment.is_scanned is True
    assert attachment.is_safe is False
