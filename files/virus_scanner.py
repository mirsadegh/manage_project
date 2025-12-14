# files/virus_scanner.py

import subprocess
import logging

logger = logging.getLogger('files')


class VirusScanner:
    """
    Virus scanner using ClamAV.
    Install ClamAV: sudo apt-get install clamav clamav-daemon
    """
    
    @staticmethod
    def scan_file(file_path):
        """
        Scan a file for viruses using ClamAV.
        
        Args:
            file_path: Path to the file to scan
        
        Returns:
            tuple: (is_safe, scan_result)
        """
        try:
            # Run clamav scan
            result = subprocess.run(
                ['clamscan', '--no-summary', file_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Check result
            if result.returncode == 0:
                # File is clean
                logger.info(f"File scanned: {file_path} - CLEAN")
                return True, "Clean"
            else:
                # Virus found
                logger.warning(f"File scanned: {file_path} - INFECTED")
                return False, "Virus detected"
                
        except subprocess.TimeoutExpired:
            logger.error(f"Virus scan timeout: {file_path}")
            return False, "Scan timeout"
        except FileNotFoundError:
            # ClamAV not installed
            logger.warning("ClamAV not installed - skipping virus scan")
            return True, "Scanner not available"
        except Exception as e:
            logger.error(f"Virus scan error: {str(e)}")
            return True, f"Scan error: {str(e)}"
    
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