import factory
from factory import fuzzy, SubFactory
from django.utils import timezone
from django.core.files.base import ContentFile
from accounts.tests.factories import UserFactory
from projects.tests.factories import ProjectFactory
from tasks.tests.factories import TaskFactory
from ..models import Attachment


class AttachmentFactory(factory.django.DjangoModelFactory):
    """Factory for Attachment model."""
    
    class Meta:
        model = Attachment
    
    content_type = factory.LazyAttribute(lambda obj: obj._get_content_type())
    object_id = fuzzy.FuzzyInteger(1, 1000)
    uploaded_by = SubFactory(UserFactory)
    original_filename = factory.Faker("file_name", extension="pdf")
    file = factory.django.FileField()
    description = factory.Faker("sentence", nb_words=10)
    file_size = fuzzy.FuzzyInteger(1024, 10485760)  # 1KB to 10MB
    file_hash = factory.Faker("sha256")
    download_count = 0
    is_virus_scanned = True
    virus_scan_result = Attachment.VirusScanResult.CLEAN
    uploaded_at = factory.LazyFunction(timezone.now)
    
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Handle content_object properly
        content_object = kwargs.pop('content_object', None)
        
        # Generate file content if not provided
        if 'file' not in kwargs:
            file_content = b"Test file content for testing purposes."
            kwargs['file'] = ContentFile(file_content, kwargs.get('original_filename', 'test.txt'))
        
        if content_object:
            instance = model_class(**kwargs)
            instance.content_object = content_object
            instance.save()
            return instance
        return super()._create(model_class, *args, **kwargs)


class ProjectAttachmentFactory(AttachmentFactory):
    """Factory for project attachments."""
    
    content_object = SubFactory(ProjectFactory)
    original_filename = factory.Faker("file_name", extension="pdf")


class TaskAttachmentFactory(AttachmentFactory):
    """Factory for task attachments."""
    
    content_object = SubFactory(TaskFactory)
    original_filename = factory.Faker("file_name", extension="docx")


class ImageAttachmentFactory(AttachmentFactory):
    """Factory for image attachments."""
    
    original_filename = factory.Faker("file_name", extension="jpg")
    file = factory.django.ImageField()
    is_image = True
    image_width = fuzzy.FuzzyInteger(400, 2000)
    image_height = fuzzy.FuzzyInteger(300, 1500)
    
    @factory.post_generation
    def generate_thumbnail(self, create, extracted, **kwargs):
        """Generate thumbnail for image."""
        if create and self.is_image:
            # In real implementation, this would generate a thumbnail
            # For testing, we'll just set a placeholder
            self.thumbnail = self.file
            self.save()


class PDFAttachmentFactory(AttachmentFactory):
    """Factory for PDF attachments."""
    
    original_filename = factory.Faker("file_name", extension="pdf")
    file = factory.django.FileField(
        data=b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n2 0 obj\n<<\n/Type /Pages\n/Kids [3 0 R]\n/Count 1\n>>\nendobj\n3 0 obj\n<<\n/Type /Page\n/Parent 2 0 R\n/MediaBox [0 0 612 792]\n>>\nendobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer\n<<\n/Size 4\n/Root 1 0 R\n>>\nstartxref\n179\n%%EOF",
        filename="test.pdf"
    )


class InfectedAttachmentFactory(AttachmentFactory):
    """Factory for infected attachments (for testing virus scanning)."""
    
    is_virus_scanned = True
    virus_scan_result = Attachment.VirusScanResult.INFECTED
    file_hash = factory.Faker("sha256")


class PendingScanAttachmentFactory(AttachmentFactory):
    """Factory for attachments pending virus scan."""
    
    is_virus_scanned = False
    virus_scan_result = Attachment.VirusScanResult.PENDING


class LargeAttachmentFactory(AttachmentFactory):
    """Factory for large attachments (for testing size limits)."""
    
    file_size = fuzzy.FuzzyInteger(10485761, 52428800)  # 10MB+ to 50MB
    file = factory.django.FileField(
        data=b"x" * 15000000,  # 15MB file
        filename="large_file.dat"
    )


class DownloadedAttachmentFactory(AttachmentFactory):
    """Factory for attachments with download history."""
    
    download_count = fuzzy.FuzzyInteger(1, 100)
    
    @factory.post_generation
    def create_download_log(self, create, extracted, **kwargs):
        """Create download log entries."""
        if create:
            # In real implementation, this would create download log entries
            # For testing, we'll just set the count
            pass


class AttachmentWithMetadataFactory(AttachmentFactory):
    """Factory for attachments with complete metadata."""
    
    file_size = fuzzy.FuzzyInteger(5000, 2000000)
    file_hash = factory.Faker("sha256")
    description = factory.Faker("paragraph", nb_sentences=2)
    
    @factory.post_generation
    def add_exif_data(self, create, extracted, **kwargs):
        """Add EXIF data for images."""
        if create and self.is_image:
            # In real implementation, this would extract EXIF data
            pass


class AttachmentBatchFactory:
    """Factory for creating batches of attachments."""
    
    @staticmethod
    def create_for_project(project, count=5, uploaded_by=None):
        """Create multiple attachments for a project."""
        if uploaded_by is None:
            uploaded_by = project.owner
        
        attachments = []
        for i in range(count):
            attachment = AttachmentFactory(
                content_object=project,
                uploaded_by=uploaded_by,
                description=f"Project file {i+1}"
            )
            attachments.append(attachment)
        return attachments
    
    @staticmethod
    def create_for_task(task, count=3, uploaded_by=None):
        """Create multiple attachments for a task."""
        if uploaded_by is None:
            uploaded_by = task.created_by
        
        attachments = []
        for i in range(count):
            attachment = AttachmentFactory(
                content_object=task,
                uploaded_by=uploaded_by,
                description=f"Task file {i+1}"
            )
            attachments.append(attachment)
        return attachments
    
    @staticmethod
    def create_mixed_attachments(content_object, uploaded_by=None):
        """Create mixed types of attachments."""
        if uploaded_by is None:
            uploaded_by = getattr(content_object, 'owner', getattr(content_object, 'created_by', UserFactory()))
        
        attachments = [
            PDFAttachmentFactory(
                content_object=content_object,
                uploaded_by=uploaded_by
            ),
            ImageAttachmentFactory(
                content_object=content_object,
                uploaded_by=uploaded_by
            ),
            AttachmentFactory(
                content_object=content_object,
                uploaded_by=uploaded_by,
                original_filename="document.txt"
            )
        ]
        return attachments


class VirusScanResultFactory:
    """Factory for simulating virus scan results."""
    
    @staticmethod
    def simulate_scan(attachment, result="CLEAN"):
        """Simulate virus scan result for an attachment."""
        attachment.is_virus_scanned = True
        
        result_map = {
            "CLEAN": Attachment.VirusScanResult.CLEAN,
            "INFECTED": Attachment.VirusScanResult.INFECTED,
            "ERROR": Attachment.VirusScanResult.ERROR,
            "PENDING": Attachment.VirusScanResult.PENDING
        }
        
        attachment.virus_scan_result = result_map.get(result, Attachment.VirusScanResult.CLEAN)
        attachment.save()
        return attachment
