# files/tasks.py

import logging

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded
from django.db import transaction

from .virus_scanner import VirusScanner


logger = logging.getLogger('files')


@shared_task(
    bind=True,
    max_retries=3,
    retry_backoff=60,
    soft_time_limit=300,
)
def scan_uploaded_file(self, attachment_id):
    """
    Celery task to scan uploaded files asynchronously.

    H2: bound task with bounded retries, exponential backoff, soft timeout,
    and a final-failure path that marks the attachment unsafe so it is
    blocked by the C2b download gate instead of being silently stranded.
    """
    try:
        return VirusScanner.scan_file_async(attachment_id)
    except SoftTimeLimitExceeded as exc:
        # Soft limit hit mid-scan: requeue with backoff.
        try:
            raise self.retry(countdown=60)
        except MaxRetriesExceededError:
            logger.error(
                'Scan timed out for attachment %s after max retries', attachment_id,
            )
            _mark_unsafe(attachment_id, reason='scan timeout')
            return False, 'Scan timed out'
    except Exception as exc:
        # Transient failure (DB blip, clamd hiccup): retry.
        try:
            raise self.retry(countdown=60)
        except MaxRetriesExceededError:
            logger.error(
                'Scan failed for attachment %s after max retries: %s',
                attachment_id, exc,
            )
            _mark_unsafe(attachment_id, reason=f'scan failed: {exc}')
            return False, f'Scan failed: {exc}'


def _mark_unsafe(attachment_id, *, reason):
    """Persist is_safe=False for an attachment that could not be scanned.

    H2: ensure final-failure attachments fail closed instead of remaining in
    the default is_scanned=False, is_safe=False limbo silently.
    """
    from .models import Attachment

    try:
        with transaction.atomic():
            attachment = Attachment.objects.select_for_update().get(id=attachment_id)
            attachment.is_scanned = True
            attachment.is_safe = False
            attachment.save(update_fields=['is_scanned', 'is_safe'])
    except Exception as exc:
        logger.error(
            'Failed to mark attachment %s unsafe after scan failure (%s): %s',
            attachment_id, reason, exc,
        )
