import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from projects.models import Project, ProjectMember
from comments.models import Comment

User = get_user_model()

# Base path for comment endpoints
COMMENTS_BASE = '/api/comments/comments'


@pytest.fixture
def users():
    owner = User.objects.create_user(email='owner@example.com', username='owner',
                                     password='pw', role='PM')
    member = User.objects.create_user(email='member@example.com', username='member',
                                      password='pw', role='DEV')
    outsider = User.objects.create_user(email='out@example.com', username='out',
                                        password='pw', role='DEV')
    return owner, member, outsider


@pytest.fixture
def project(users):
    owner, member, _ = users
    p = Project.objects.create(name='P1', slug='p1', owner=owner)
    ProjectMember.objects.create(project=p, user=member,
                                 role=ProjectMember.Role.MEMBER, is_active=True)
    return p


def _client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def _make_comment(author, target):
    ct = ContentType.objects.get_for_model(target)
    return Comment.objects.create(author=author, text='secret',
                                  content_type=ct, object_id=target.id)


# ─────────────────────────────────────────────
# BOLA: Read access tests
# ─────────────────────────────────────────────

@pytest.mark.django_db
def test_outsider_cannot_retrieve_comment_by_id(users, project):
    """An outsider must not read a comment on a project they don't belong to."""
    owner, member, outsider = users
    comment = _make_comment(owner, project)
    resp = _client(outsider).get(f'{COMMENTS_BASE}/{comment.id}/')
    # 404 is also acceptable (hides resource existence — more secure)
    assert resp.status_code in [403, 404]


@pytest.mark.django_db
def test_member_can_retrieve_comment_on_their_project(users, project):
    """A project member can read comments on their project."""
    owner, member, outsider = users
    comment = _make_comment(owner, project)
    resp = _client(member).get(f'{COMMENTS_BASE}/{comment.id}/')
    assert resp.status_code == 200
    assert resp.data['id'] == comment.id


@pytest.mark.django_db
def test_outsider_list_without_filter_leaks_nothing(users, project):
    """An outsider listing comments must not see any comments."""
    owner, member, outsider = users
    _make_comment(owner, project)
    resp = _client(outsider).get(f'{COMMENTS_BASE}/')
    # Either forbidden, or returns an empty scoped list
    assert resp.status_code in [200, 403, 404]
    if resp.status_code == 200:
        results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
        assert len(results) == 0


@pytest.mark.django_db
def test_member_list_without_filter_is_scoped(users, project):
    """A member listing comments only sees comments on their own projects."""
    owner, member, outsider = users
    mine = _make_comment(owner, project)
    # A comment on a project the member cannot access must NOT leak.
    other_owner = User.objects.create_user(email='o2@example.com', username='o2',
                                           password='pw', role='PM')
    other_project = Project.objects.create(name='P2', slug='p2', owner=other_owner)
    _make_comment(other_owner, other_project)
    resp = _client(member).get(f'{COMMENTS_BASE}/')
    assert resp.status_code == 200
    results = resp.data['results'] if isinstance(resp.data, dict) else resp.data
    ids = [c['id'] for c in results]
    assert mine.id in ids
    assert len(ids) == 1  # only the accessible project's comment


# ─────────────────────────────────────────────
# BOLA: Statistics & reactions
# ─────────────────────────────────────────────

@pytest.mark.django_db
def test_statistics_requires_project_membership(users, project):
    """Comment statistics must be gated by project membership."""
    owner, member, outsider = users
    _make_comment(owner, project)
    # Outsider is denied
    resp = _client(outsider).get(f'{COMMENTS_BASE}/statistics/project/{project.id}/')
    assert resp.status_code in [403, 404]
    # Member is allowed
    resp2 = _client(member).get(f'{COMMENTS_BASE}/statistics/project/{project.id}/')
    assert resp2.status_code == 200


@pytest.mark.django_db
def test_react_requires_project_membership(users, project):
    """Reacting to a comment must be gated by project membership."""
    owner, member, outsider = users
    comment = _make_comment(owner, project)
    # Outsider is denied
    resp = _client(outsider).post(
        f'{COMMENTS_BASE}/{comment.id}/react/',
        {'reaction_type': 'LIKE'}, format='json'
    )
    assert resp.status_code in [403, 404]
    # Member is allowed
    resp2 = _client(member).post(
        f'{COMMENTS_BASE}/{comment.id}/react/',
        {'reaction_type': 'LIKE'}, format='json'
    )
    assert resp2.status_code in (200, 201)


@pytest.mark.django_db
def test_unreact_requires_project_membership(users, project):
    """Unreacting from a comment must be gated by project membership."""
    owner, member, outsider = users
    comment = _make_comment(owner, project)
    resp = _client(outsider).delete(
        f'{COMMENTS_BASE}/{comment.id}/unreact/',
        {'reaction_type': 'LIKE'}, format='json'
    )
    assert resp.status_code in [403, 404]


# ─────────────────────────────────────────────
# BOLA: Edit/Delete permissions
# ─────────────────────────────────────────────

@pytest.mark.django_db
def test_member_cannot_edit_others_comment(users, project):
    """BOLA: a project member who is NOT the author must not edit a comment."""
    owner, member, outsider = users
    comment = _make_comment(owner, project)  # author == owner
    resp = _client(member).patch(
        f'{COMMENTS_BASE}/{comment.id}/', {'text': 'hacked by member'}
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_member_cannot_delete_others_comment(users, project):
    """BOLA: a project member who is NOT the author must not delete a comment."""
    owner, member, outsider = users
    comment = _make_comment(owner, project)
    resp = _client(member).delete(f'{COMMENTS_BASE}/{comment.id}/')
    assert resp.status_code == 403


@pytest.mark.django_db
def test_author_can_edit_own_comment(users, project):
    """Regression guard: the author can still edit their own comment."""
    owner, member, outsider = users
    comment = _make_comment(owner, project)
    resp = _client(owner).patch(
        f'{COMMENTS_BASE}/{comment.id}/', {'text': 'edited by author'}
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_admin_can_delete_any_comment(users, project):
    """Regression guard: an ADMIN can still delete any comment."""
    owner, member, outsider = users
    admin = User.objects.create_user(email='admin@example.com', username='admin',
                                     password='pw', role='ADMIN')
    comment = _make_comment(owner, project)
    resp = _client(admin).delete(f'{COMMENTS_BASE}/{comment.id}/')
    assert resp.status_code == 204