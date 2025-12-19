import factory
from factory import fuzzy
from django.contrib.auth import get_user_model
from ..models import CustomUser

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    """Factory for CustomUser model."""
    
    class Meta:
        model = User
    
    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    password = factory.PostGenerationMethodCall("set_password", "password")
    role = fuzzy.FuzzyChoice(
        [User.Role.DEVELOPER, User.Role.DESIGNER, User.Role.CLIENT]
    )
    phone_number = factory.Faker("phone_number")
    bio = factory.Faker("paragraph", nb_sentences=3)
    job_title = factory.Faker("job")
    department = factory.Faker("company")
    is_available = True
    skills = factory.LazyFunction(lambda: [
        "Python", "Django", "JavaScript", "React", "Docker"
    ])
    hourly_rate = fuzzy.FuzzyDecimal(20.0, 200.0, 2)
    is_active = True


class AdminUserFactory(UserFactory):
    """Factory for admin users."""
    
    role = User.Role.ADMIN
    is_staff = True
    is_superuser = True


class ManagerUserFactory(UserFactory):
    """Factory for project manager users."""
    
    role = fuzzy.FuzzyChoice(
        [User.Role.PROJECT_MANAGER, User.Role.TEAM_LEAD]
    )


class DeveloperUserFactory(UserFactory):
    """Factory for developer users."""
    
    role = User.Role.DEVELOPER


class DesignerUserFactory(UserFactory):
    """Factory for designer users."""
    
    role = User.Role.DESIGNER


class ClientUserFactory(UserFactory):
    """Factory for client users."""
    
    role = User.Role.CLIENT


class InactiveUserFactory(UserFactory):
    """Factory for inactive users."""
    
    is_active = False


class UnavailableUserFactory(UserFactory):
    """Factory for unavailable users."""
    
    is_available = False
