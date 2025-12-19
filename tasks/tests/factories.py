import factory
from factory import fuzzy, SubFactory
from django.utils import timezone
from datetime import timedelta
from accounts.tests.factories import UserFactory
from projects.tests.factories import ProjectFactory
from ..models import Task, TaskList, TaskDependency


class TaskListFactory(factory.django.DjangoModelFactory):
    """Factory for TaskList model."""
    
    class Meta:
        model = TaskList
    
    name = factory.Faker("catch_phrase")
    description = factory.Faker("paragraph", nb_sentences=3)
    project = SubFactory(ProjectFactory)
    created_by = SubFactory(UserFactory)
    is_active = True
    order = fuzzy.FuzzyInteger(0, 100)


class TaskFactory(factory.django.DjangoModelFactory):
    """Factory for Task model."""
    
    class Meta:
        model = Task
    
    title = factory.Faker("catch_phrase")
    description = factory.Faker("paragraph", nb_sentences=5)
    project = SubFactory(ProjectFactory)
    task_list = SubFactory(TaskListFactory)
    created_by = SubFactory(UserFactory)
    assignee = SubFactory(UserFactory)
    status = fuzzy.FuzzyChoice(
        [Task.Status.TODO, Task.Status.IN_PROGRESS, 
         Task.Status.IN_REVIEW, Task.Status.COMPLETED, Task.Status.CANCELLED]
    )
    priority = fuzzy.FuzzyChoice(
        [Task.Priority.LOW, Task.Priority.MEDIUM, 
         Task.Priority.HIGH, Task.Priority.URGENT]
    )
    estimated_hours = fuzzy.FuzzyDecimal(1.0, 40.0, 2)
    actual_hours = fuzzy.FuzzyDecimal(0.0, 50.0, 2)
    start_date = factory.LazyFunction(lambda: timezone.now().date())
    due_date = factory.LazyAttribute(
        lambda obj: obj.start_date + timedelta(days=fuzzy.FuzzyInteger(1, 30).fuzz())
    )
    completed_date = factory.LazyAttribute(
        lambda obj: timezone.now() if obj.status == Task.Status.COMPLETED else None
    )
    is_active = True
    
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Ensure task_list belongs to the same project
        if 'task_list' not in kwargs and 'project' in kwargs:
            kwargs['task_list'] = TaskListFactory(project=kwargs['project'])
        return super()._create(model_class, *args, **kwargs)


class CompletedTaskFactory(TaskFactory):
    """Factory for completed tasks."""
    
    status = Task.Status.COMPLETED
    completed_date = factory.LazyFunction(timezone.now)
    actual_hours = factory.LazyAttribute(
        lambda obj: obj.estimated_hours * fuzzy.FuzzyDecimal(0.8, 1.5).fuzz()
    )


class HighPriorityTaskFactory(TaskFactory):
    """Factory for high priority tasks."""
    
    priority = Task.Priority.HIGH


class OverdueTaskFactory(TaskFactory):
    """Factory for overdue tasks."""
    
    due_date = factory.LazyFunction(
        lambda: (timezone.now() - timedelta(days=fuzzy.FuzzyInteger(1, 10).fuzz())).date()
    )
    status = fuzzy.FuzzyChoice([Task.Status.TODO, Task.Status.IN_PROGRESS])


class TaskDependencyFactory(factory.django.DjangoModelFactory):
    """Factory for TaskDependency model."""
    
    class Meta:
        model = TaskDependency
    
    task = SubFactory(TaskFactory)
    depends_on = SubFactory(TaskFactory)
    dependency_type = TaskDependency.DependencyType.FINISH_TO_START
    
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # Ensure tasks are in the same project
        if 'depends_on' in kwargs and 'task' in kwargs:
            kwargs['depends_on'].project = kwargs['task'].project
            kwargs['depends_on'].save()
        return super()._create(model_class, *args, **kwargs)


class BlockerDependencyFactory(TaskDependencyFactory):
    """Factory for blocker dependencies."""
    
    dependency_type = TaskDependency.DependencyType.BLOCKS


class TaskListWithTasksFactory(TaskListFactory):
    """Factory that creates a task list with multiple tasks."""
    
    @factory.post_generation
    def tasks(self, create, extracted, **kwargs):
        if create:
            # Create 3-7 tasks in the list
            task_count = fuzzy.FuzzyInteger(3, 7).fuzz()
            for _ in range(task_count):
                TaskFactory(
                    task_list=self,
                    project=self.project,
                    created_by=self.created_by
                )
        if extracted:
            # Add specified tasks
            for task in extracted:
                task.task_list = self
                task.project = self.project
                task.save()


class ProjectWithTasksFactory(ProjectFactory):
    """Factory that creates a project with tasks."""
    
    @factory.post_generation
    def with_tasks(self, create, extracted, **kwargs):
        if create:
            # Create task list and tasks
            task_list = TaskListFactory(project=self, created_by=self.owner)
            task_count = extracted if extracted is not None else fuzzy.FuzzyInteger(5, 15).fuzz()
            
            for i in range(task_count):
                TaskFactory(
                    project=self,
                    task_list=task_list,
                    created_by=self.owner,
                    assignee=UserFactory()
                )
