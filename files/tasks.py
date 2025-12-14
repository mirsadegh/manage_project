# files/tasks.py

from celery import shared_task
from .virus_scanner import VirusScanner


@shared_task
def scan_uploaded_file(attachment_id):
    """
    Celery task to scan uploaded files asynchronously.
    
    Args:
        attachment_id: ID of the attachment to scan
    
    Returns:
        tuple: (is_safe, scan_result)
    """
    return VirusScanner.scan_file_async(attachment_id)