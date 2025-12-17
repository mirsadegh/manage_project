import subprocess
import logging
import clamd



logger = logging.getLogger('files')


class VirusScanner:
    """
    Virus scanner using ClamAV.
    Install ClamAV: sudo apt-get install clamav clamav-daemon
    """

    @staticmethod
    def scan_file(file_path: str) -> tuple[bool, str]:
        """
        Scan a file for viruses using ClamAV daemon.
        Returns (is_safe, message)
        """
        try:
            cd = clamd.ClamdUnixSocket()
            # Test connection
            cd.ping()
        except (clamd.ConnectionError, FileNotFoundError):
            # CRITICAL FIX: Fail closed when scanner unavailable
            logger.error("ClamAV not available - rejecting file upload")
            return False, "Virus scanner unavailable - cannot process file"
        
        try:
            scan_result = cd.scan(file_path)
            if scan_result is None:
                logger.info(f"File scanned: {file_path} - CLEAN")
                return True, "File is clean"
            
            # File is infected
            # The result format is {'/path/to/file': ('FOUND', 'Virus.Name')}
            status, virus_name = list(scan_result.values())[0]
            if status == 'FOUND':
                logger.warning(f"File scanned: {file_path} - INFECTED with {virus_name}")
                return False, f"Virus detected: {virus_name}"
            
            # Fallback for other statuses
            logger.warning(f"File scanned: {file_path} - UNKNOWN STATUS: {scan_result}")
            return False, f"Scan result unknown: {scan_result}"

        except Exception as e:
            # CRITICAL FIX: Fail closed on scanning errors
            logger.error(f"Virus scan failed: {str(e)}")
            return False, f"Virus scan failed: {str(e)}"
   
    @staticmethod
    def scan_file_async(attachment_id):
        """
        Asynchronous virus scan using Celery.
        
        Args:
            attachment_id: ID of the attachment to scan
        """
        from .models import Attachment
        
        try:
            attachment = Attachment.objects.get(id=attachment_id)
            
            # Scan the file
            is_safe, result = VirusScanner.scan_file(attachment.file.path)
            
            # Update attachment
            attachment.is_scanned = True
            attachment.is_safe = is_safe
            attachment.save(update_fields=['is_scanned', 'is_safe'])
            
            # If virus found, notify admin and uploader
            if not is_safe:
                from notifications.models import Notification
                from accounts.models import CustomUser
                
                # Notify uploader
                Notification.objects.create(
                    recipient=attachment.uploaded_by,
                    notification_type='STATUS_CHANGE',
                    title='File Flagged',
                    message=f'Your uploaded file "{attachment.original_filename}" was flagged by virus scanner',
                    content_object=attachment
                )
                
                # Notify admins
                admins = CustomUser.objects.filter(role='ADMIN')
                for admin in admins:
                    Notification.objects.create(
                        recipient=admin,
                        notification_type='STATUS_CHANGE',
                        title='Unsafe File Detected',
                        message=f'File "{attachment.original_filename}" uploaded by {attachment.uploaded_by.username} was flagged',
                        content_object=attachment
                    )
            
            return is_safe, result
            
        except Attachment.DoesNotExist:
            logger.error(f"Attachment {attachment_id} not found for scanning")
            return False, "Attachment not found"