"""
Performance tests for critical endpoints and operations.
"""
import pytest
import time
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from django.test.utils import override_settings
from accounts.tests.factories import UserFactory, ManagerUserFactory
from projects.tests.factories import ProjectFactory, ProjectMemberFactory
from tasks.tests.factories import TaskFactory, TaskListFactory

User = get_user_model()


@pytest.mark.performance
@pytest.mark.django_db
class TestAPIPerformance:
    """Test API endpoint performance."""
    
    def test_user_list_performance(self, api_client):
        """Test user list endpoint performance."""
        # Create many users
        UserFactory.create_batch(100)
        
        start_time = time.time()
        response = api_client.get(reverse('user-list'))
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        response_time = end_time - start_time
        assert response_time < 1.0, f"User list took {response_time:.2f}s, should be < 1.0s"
    
    def test_project_list_performance(self, api_client):
        """Test project list endpoint performance."""
        # Create many projects
        ManagerUserFactory.create_batch(50)
        ProjectFactory.create_batch(50)
        
        start_time = time.time()
        response = api_client.get(reverse('project-list'))
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        response_time = end_time - start_time
        assert response_time < 1.5, f"Project list took {response_time:.2f}s, should be < 1.5s"
    
    def test_task_list_performance(self, api_client):
        """Test task list endpoint performance."""
        # Create project with many tasks
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        task_list = TaskListFactory(project=project, created_by=manager)
        TaskFactory.create_batch(100, project=project, task_list=task_list, created_by=manager)
        
        start_time = time.time()
        response = api_client.get(reverse('task-list'))
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        response_time = end_time - start_time
        assert response_time < 2.0, f"Task list took {response_time:.2f}s, should be < 2.0s"
    
    def test_filtered_task_list_performance(self, api_client):
        """Test filtered task list performance."""
        # Create project with many tasks
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        task_list = TaskListFactory(project=project, created_by=manager)
        
        # Create tasks with different statuses
        for i in range(50):
            TaskFactory(
                project=project,
                task_list=task_list,
                created_by=manager,
                status=['TODO', 'IN_PROGRESS', 'COMPLETED'][i % 3]
            )
        
        # Test with filter
        start_time = time.time()
        response = api_client.get(f"{reverse('task-list')}?status=IN_PROGRESS")
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        response_time = end_time - start_time
        assert response_time < 1.0, f"Filtered task list took {response_time:.2f}s, should be < 1.0s"
    
    def test_search_performance(self, api_client):
        """Test search endpoint performance."""
        # Create searchable data
        manager = ManagerUserFactory()
        projects = ProjectFactory.create_batch(
            50,
            owner=manager,
            name=factory.Faker("word").generate() + " UniqueSearchTerm"
        )
        
        start_time = time.time()
        response = api_client.get(f"{reverse('project-list')}?search=UniqueSearchTerm")
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        response_time = end_time - start_time
        assert response_time < 1.5, f"Search took {response_time:.2f}s, should be < 1.5s"


@pytest.mark.performance
@pytest.mark.django_db
class TestDatabasePerformance:
    """Test database operation performance."""
    
    def test_large_project_query_performance(self, api_client):
        """Test performance of queries on large projects."""
        # Create complex project structure
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        
        # Add many members
        members = UserFactory.create_batch(50)
        for member in members:
            ProjectMemberFactory(project=project, user=member)
        
        # Create many task lists
        task_lists = TaskListFactory.create_batch(
            10,
            project=project,
            created_by=manager
        )
        
        # Create many tasks
        for task_list in task_lists:
            TaskFactory.create_batch(
                20,
                project=project,
                task_list=task_list,
                created_by=manager
            )
        
        # Test project detail query
        with override_settings(DEBUG=True):
            from django.test.utils import override_settings
            from django.db import connection
            
            # Reset query count
            connection.queries_log.clear()
            
            start_time = time.time()
            response = api_client.get(reverse('project-detail', kwargs={'pk': project.id}))
            end_time = time.time()
            
            assert response.status_code == status.HTTP_200_OK
            
            query_count = len(connection.queries)
            response_time = end_time - start_time
            
            # Should use reasonable number of queries
            assert query_count < 50, f"Project detail used {query_count} queries, should be < 50"
            assert response_time < 2.0, f"Project detail took {response_time:.2f}s, should be < 2.0s"
    
    def test_task_statistics_query_performance(self, api_client):
        """Test performance of task statistics queries."""
        # Create project with many tasks
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        task_list = TaskListFactory(project=project, created_by=manager)
        TaskFactory.create_batch(200, project=project, task_list=task_list, created_by=manager)
        
        with override_settings(DEBUG=True):
            from django.db import connection
            
            connection.queries_log.clear()
            
            start_time = time.time()
            response = api_client.get(f"{reverse('task-list')}?project={project.id}")
            end_time = time.time()
            
            assert response.status_code == status.HTTP_200_OK
            
            query_count = len(connection.queries)
            response_time = end_time - start_time
            
            assert query_count < 30, f"Task list used {query_count} queries, should be < 30"
            assert response_time < 1.5, f"Task list with stats took {response_time:.2f}s, should be < 1.5s"


@pytest.mark.performance
@pytest.mark.django_db
class TestPaginationPerformance:
    """Test pagination performance with large datasets."""
    
    def test_pagination_performance(self, api_client):
        """Test pagination doesn't degrade with large datasets."""
        # Create many tasks
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        task_list = TaskListFactory(project=project, created_by=manager)
        TaskFactory.create_batch(1000, project=project, task_list=task_list, created_by=manager)
        
        # Test first page
        start_time = time.time()
        response = api_client.get(reverse('task-list'))
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        first_page_time = end_time - start_time
        assert first_page_time < 2.0, f"First page took {first_page_time:.2f}s, should be < 2.0s"
        
        # Test middle page
        start_time = time.time()
        response = api_client.get(f"{reverse('task-list')}?page=50")
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        middle_page_time = end_time - start_time
        assert middle_page_time < 1.5, f"Middle page took {middle_page_time:.2f}s, should be < 1.5s"
        
        # Test last page
        start_time = time.time()
        response = api_client.get(f"{reverse('task-list')}?page=100")
        end_time = time.time()
        
        assert response.status_code == status.HTTP_200_OK
        last_page_time = end_time - start_time
        assert last_page_time < 1.0, f"Last page took {last_page_time:.2f}s, should be < 1.0s"
    
    def test_page_size_performance(self, api_client):
        """Test different page sizes don't affect performance significantly."""
        # Create many tasks
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        task_list = TaskListFactory(project=project, created_by=manager)
        TaskFactory.create_batch(500, project=project, task_list=task_list, created_by=manager)
        
        # Test different page sizes
        page_sizes = [10, 20, 50, 100]
        
        for page_size in page_sizes:
            start_time = time.time()
            response = api_client.get(f"{reverse('task-list')}?page_size={page_size}")
            end_time = time.time()
            
            assert response.status_code == status.HTTP_200_OK
            response_time = end_time - start_time
            
            # Larger pages should take proportionally more time but not exponentially
            max_time = 2.0 * (page_size / 20)
            assert response_time < max_time, f"Page size {page_size} took {response_time:.2f}s, should be < {max_time:.2f}s"


@pytest.mark.performance
@pytest.mark.django_db
class TestConcurrentPerformance:
    """Test performance under concurrent load."""
    
    def test_concurrent_user_creation(self, api_client):
        """Test user creation under concurrent load."""
        import threading
        import queue
        
        results = queue.Queue()
        
        def create_user():
            try:
                start_time = time.time()
                response = api_client.post(reverse('register'), {
                    'username': f'user_{threading.get_ident()}',
                    'email': f'user_{threading.get_ident()}@test.com',
                    'password': 'TestPass123!',
                    'password2': 'TestPass123!',
                    'first_name': 'Test',
                    'last_name': 'User',
                    'role': 'DEV'
                })
                end_time = time.time()
                results.put({
                    'status': response.status_code,
                    'time': end_time - start_time
                })
            except Exception as e:
                results.put({'error': str(e)})
        
        # Create 10 concurrent users
        threads = []
        start_time = time.time()
        
        for _ in range(10):
            thread = threading.Thread(target=create_user)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        total_time = time.time() - start_time
        
        # Check results
        successful = 0
        avg_response_time = 0
        
        while not results.empty():
            result = results.get()
            if 'status' in result:
                if result['status'] == status.HTTP_201_CREATED:
                    successful += 1
                avg_response_time += result['time']
        
        avg_response_time /= successful if successful > 0 else 1
        
        assert successful >= 8, f"Only {successful}/10 users created successfully"
        assert total_time < 5.0, f"Concurrent creation took {total_time:.2f}s, should be < 5.0s"
        assert avg_response_time < 1.0, f"Average response time {avg_response_time:.2f}s, should be < 1.0s"
    
    def test_concurrent_task_access(self, api_client):
        """Test concurrent task access performance."""
        import threading
        import queue
        
        # Setup data
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        task_list = TaskListFactory(project=project, created_by=manager)
        tasks = TaskFactory.create_batch(
            50,
            project=project,
            task_list=task_list,
            created_by=manager
        )
        
        results = queue.Queue()
        
        def access_tasks():
            try:
                start_time = time.time()
                response = api_client.get(reverse('task-list'))
                end_time = time.time()
                results.put({
                    'status': response.status_code,
                    'time': end_time - start_time,
                    'count': len(response.data.get('results', []))
                })
            except Exception as e:
                results.put({'error': str(e)})
        
        # Create 20 concurrent accesses
        threads = []
        
        for _ in range(20):
            thread = threading.Thread(target=access_tasks)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Check results
        successful = 0
        avg_response_time = 0
        avg_count = 0
        
        while not results.empty():
            result = results.get()
            if 'status' in result:
                if result['status'] == status.HTTP_200_OK:
                    successful += 1
                avg_response_time += result['time']
                avg_count += result['count']
        
        avg_response_time /= successful if successful > 0 else 1
        avg_count /= successful if successful > 0 else 1
        
        assert successful >= 18, f"Only {successful}/20 accesses successful"
        assert avg_response_time < 2.0, f"Average response time {avg_response_time:.2f}s, should be < 2.0s"
        assert 15 <= avg_count <= 25, f"Average count {avg_count}, should be ~20"


@pytest.mark.performance
@pytest.mark.django_db
class TestMemoryUsage:
    """Test memory usage during operations."""
    
    def test_large_dataset_memory_usage(self, api_client):
        """Test memory usage with large datasets."""
        import gc
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Create large dataset
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        task_list = TaskListFactory(project=project, created_by=manager)
        
        # Create tasks in batches to avoid memory spikes
        for batch in range(10):
            TaskFactory.create_batch(
                50,
                project=project,
                task_list=task_list,
                created_by=manager
            )
            gc.collect()  # Force garbage collection
        
        # Test memory after creation
        creation_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Test memory during API calls
        max_memory = creation_memory
        
        for _ in range(5):
            response = api_client.get(reverse('task-list'))
            assert response.status_code == status.HTTP_200_OK
            
            current_memory = process.memory_info().rss / 1024 / 1024
            max_memory = max(max_memory, current_memory)
            gc.collect()
        
        # Memory growth should be reasonable
        memory_growth = max_memory - initial_memory
        assert memory_growth < 100, f"Memory grew by {memory_growth:.2f}MB, should be < 100MB"
    
    def test_pagination_memory_efficiency(self, api_client):
        """Test that pagination reduces memory usage."""
        import gc
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        # Create dataset
        manager = ManagerUserFactory()
        project = ProjectFactory(owner=manager)
        task_list = TaskListFactory(project=project, created_by=manager)
        TaskFactory.create_batch(200, project=project, task_list=task_list, created_by=manager)
        
        # Test full list memory
        gc.collect()
        before_full = process.memory_info().rss / 1024 / 1024
        
        response = api_client.get(reverse('task-list'))
        assert response.status_code == status.HTTP_200_OK
        
        gc.collect()
        after_full = process.memory_info().rss / 1024 / 1024
        full_memory_usage = after_full - before_full
        
        # Test paginated list memory
        gc.collect()
        before_paginated = process.memory_info().rss / 1024 / 1024
        
        response = api_client.get(f"{reverse('task-list')}?page_size=20")
        assert response.status_code == status.HTTP_200_OK
        
        gc.collect()
        after_paginated = process.memory_info().rss / 1024 / 1024
        paginated_memory_usage = after_paginated - before_paginated
        
        # Paginated should use significantly less memory
        assert paginated_memory_usage < full_memory_usage * 0.5, \
            f"Paginated memory {paginated_memory_usage:.2f}MB should be < 50% of full {full_memory_usage:.2f}MB"


if __name__ == "__main__":
    # Run performance tests individually for benchmarking
    pytest.main([__file__, "-v", "-s", "--disable-warnings"])
