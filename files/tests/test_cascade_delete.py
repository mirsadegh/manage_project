"""
Tests for M1 (cascade delete of Attachments when parent is deleted).
"""
import pytest
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from files.models import Attachment
from projects.models import Project
from tasks.models import Task, TaskList
from comments.models import Comment


User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='cascade_user',
        email='cascade@example.com',
        password='Test123!',
    )


@pytest.fixture
def project(db, user):
    return Project.objects.create(name='Cascade Project', owner=user)


@pytest.fixture
def project_ct(db):
    return ContentType.objects.get_for_model(Project)


@pytest.fixture
def task(project, user):
    tasklist = TaskList.objects.create(
        project=project, name='Default', created_by=user,
    )
    return Task.objects.create(
        task_list=tasklist, title='Cascade Task',
        project=project, created_by=user,
    )


@pytest.fixture
def task_ct(db):
    return ContentType.objects.get_for_model(Task)


@pytest.fixture
def other_project(db, user):
    """A separate project, unrelated to `project`."""
    return Project.objects.create(name='Other Project', owner=user)


@pytest.fixture
def other_task(other_project, user):
    """A task in other_project, unrelated to `project`."""
    tasklist = TaskList.objects.create(
        project=other_project, name='Default', created_by=user,
    )
    return Task.objects.create(
        task_list=tasklist, title='Other Task',
        project=other_project, created_by=user,
    )


def _make_attachment(content_object, user, filename='doc.txt'):
    """Helper: create an Attachment linked to the given content_object."""
    return Attachment.objects.create(
        content_object=content_object,
        uploaded_by=user,
        original_filename=filename,
        file_size=5,
        file_type='text/plain',
        file_hash='x' * 64,
        file=SimpleUploadedFile(filename, b'hello'),
        is_scanned=True,
        is_safe=True,
    )


@pytest.mark.django_db
def test_deleting_project_cascades_attachments(user, project, project_ct):
    """M1: deleting a Project deletes its Attachments."""
    a1 = _make_attachment(project, user, 'a.txt')
    a2 = _make_attachment(project, user, 'b.txt')
    a1_id, a2_id = a1.id, a2.id

    project.delete()

    assert not Attachment.objects.filter(id__in=[a1_id, a2_id]).exists()


@pytest.mark.django_db
def test_deleting_task_cascades_attachments(user, task, task_ct):
    """M1: deleting a Task deletes its Attachments."""
    a = _make_attachment(task, user, 'task.txt')
    a_id = a.id

    task.delete()

    assert not Attachment.objects.filter(id=a_id).exists()


@pytest.mark.django_db
def test_deleting_project_cascades_task_attachments(user, project, task, task_ct):
    """M1: deleting a Project also cascades its Tasks' Attachments.
    
    This is correct behavior: Task has FK to Project with CASCADE,
    so deleting Project deletes Task, which triggers our signal.
    """
    project_attachment = _make_attachment(project, user, 'proj.txt')
    task_attachment = _make_attachment(task, user, 'task.txt')

    project.delete()

    # Both should be deleted (task belongs to project)
    assert not Attachment.objects.filter(id=project_attachment.id).exists()
    assert not Attachment.objects.filter(id=task_attachment.id).exists()


@pytest.mark.django_db
def test_deleting_unrelated_project_does_not_affect_other_attachments(
    user, project, project_ct, other_task, task_ct,
):
    """M1: deleting Project A must NOT delete attachments of Task in Project B."""
    project_attachment = _make_attachment(project, user, 'proj.txt')
    task_attachment = _make_attachment(other_task, user, 'task.txt')

    project.delete()

    # Project attachment should be deleted
    assert not Attachment.objects.filter(id=project_attachment.id).exists()
    # Other project's task attachment should remain
    assert Attachment.objects.filter(id=task_attachment.id).exists()
