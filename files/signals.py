# files/signals.py

"""
M1: cascade-delete Attachments when their parent (Task, Project, Comment)
is deleted. The GenericForeignKey does not cascade by default, so without
this signal the Attachment row and its file on disk leak.

Handlers are wired in files.apps.FilesConfig.ready().
"""
import logging

from django.db.models.signals import pre_delete


logger = logging.getLogger('files')


def _cascade_attachments(sender, instance, **kwargs):
    """Delete all Attachment rows pointing at the deleted parent."""
    # Lazy import to avoid circular dependency between files and the
    # parent apps (tasks, projects, comments).
    from django.contrib.contenttypes.models import ContentType
    from .models import Attachment

    parent_ct = ContentType.objects.get_for_model(sender)
    attachments = Attachment.objects.filter(
        content_type=parent_ct, object_id=instance.pk,
    )
    count = attachments.count()
    # Attachment.delete() removes the file + thumbnail from storage.
    for attachment in attachments:
        attachment.delete()
    if count:
        logger.info(
            'M1: cascade-deleted %d attachment(s) for %s id=%s',
            count, sender.__name__, instance.pk,
        )


def connect_cascade_signals():
    """Connect pre_delete handlers for each parent model. Called from ready()."""
    from django.apps import apps

    for model_label in ('tasks.Task', 'projects.Project', 'comments.Comment'):
        try:
            model = apps.get_model(model_label)
        except LookupError:
            continue
        pre_delete.connect(_cascade_attachments, sender=model)
