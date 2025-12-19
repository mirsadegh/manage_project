import factory
from factory import fuzzy, SubFactory
from django.utils import timezone
from datetime import timedelta
from accounts.tests.factories import UserFactory, ManagerUserFactory
from ..models import Project, ProjectMember


class ProjectFactory(factory.django.DjangoModelFactory):
    """Factory for Project model."""
    
    class Meta:
        model = Project
    
    name = factory.Faker("catch_phrase")
    description = factory.Faker("paragraph", nb_sentences=5)
    owner = SubFactory(ManagerUserFactory)
    status = fuzzy.FuzzyChoice(
        [Project.Status.PLANNING, Project.Status.IN_PROGRESS, 
         Project.Status.ON_HOLD, Project.Status.COMPLETED, Project.Status.CANCELLED]
    )
    priority = fuzzy.FuzzyChoice(
        [Project.Priority.LOW, Project.Priority.MEDIUM, 
         Project.Priority.HIGH, Project.Priority.URGENT]
    )
    start_date = factory.LazyFunction(lambda: timezone.now().date())
    due_date = factory.LazyAttribute(
        lambda obj: obj.start_date + timedelta(days=fuzzy.FuzzyInteger(30, 365).fuzz())
    )
    budget = fuzzy.FuzzyDecimal(1000.0, 100000.0, 2)
    is_active = True
    
    @factory.post_generation
    def teams(self, create, extracted, **kwargs):
        if create and extracted:
            self.teams.set(extracted)


class CompletedProjectFactory(ProjectFactory):
    """Factory for completed projects."""
    
    status = Project.Status.COMPLETED
    completed_date = factory.LazyFunction(timezone.now)


class HighPriorityProjectFactory(ProjectFactory):
    """Factory for high priority projects."""
    
    priority = Project.Priority.HIGH


class ProjectMemberFactory(factory.django.DjangoModelFactory):
    """Factory for ProjectMember model."""
    
    class Meta:
        model = ProjectMember
    
    project = SubFactory(ProjectFactory)
    user = SubFactory(UserFactory)
    role = fuzzy.FuzzyChoice(
        [ProjectMember.Role.MEMBER, ProjectMember.Role.MANAGER, ProjectMember.Role.VIEWER]
    )
    joined_at = factory.LazyFunction(timezone.now)
    is_active = True


class ProjectManagerFactory(ProjectMemberFactory):
    """Factory for project managers."""
    
    role = ProjectMember.Role.MANAGER


class ProjectViewerFactory(ProjectMemberFactory):
    """Factory for project viewers."""
    
    role = ProjectMember.Role.VIEWER


class InactiveProjectMemberFactory(ProjectMemberFactory):
    """Factory for inactive project members."""
    
    is_active = False
    left_at = factory.LazyFunction(timezone.now)
