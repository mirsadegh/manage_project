from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from accounts.models import CustomUser
from .models import Project, ProjectMember


class ProjectCreationTests(APITestCase):
    """Test project creation permissions"""
    
    def setUp(self):
        self.admin = CustomUser.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='Admin123!',
            role='ADMIN'
        )
        self.manager = CustomUser.objects.create_user(
            username='manager',
            email='manager@example.com',
            password='Manager123!',
            role='PM'
        )
        self.developer = CustomUser.objects.create_user(
            username='developer',
            email='dev@example.com',
            password='Dev123!',
            role='DEV'
        )
        self.project_list_url = reverse('project-list')
    
    def test_admin_can_create_project(self):
        """Test admin can create projects"""
        self.client.force_authenticate(user=self.admin)
        data = {
            'name': 'Admin Project',
            'description': 'Test project',
            'status': 'PLANNING',
            'priority': 'HIGH'
        }
        response = self.client.post(self.project_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Project.objects.count(), 1)
    
    def test_manager_can_create_project(self):
        """Test manager can create projects"""
        self.client.force_authenticate(user=self.manager)
        data = {
            'name': 'Manager Project',
            'description': 'Test project',
            'status': 'PLANNING',
            'priority': 'MEDIUM'
        }
        response = self.client.post(self.project_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Project.objects.count(), 1)
    
    def test_developer_cannot_create_project(self):
        """Test developer cannot create projects"""
        self.client.force_authenticate(user=self.developer)
        data = {
            'name': 'Dev Project',
            'description': 'Test project',
            'status': 'PLANNING',
            'priority': 'LOW'
        }
        response = self.client.post(self.project_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Project.objects.count(), 0)
    
    def test_unauthenticated_cannot_create_project(self):
        """Test unauthenticated user cannot create projects"""
        data = {
            'name': 'Test Project',
            'description': 'Test project',
            'status': 'PLANNING'
        }
        response = self.client.post(self.project_list_url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ProjectAccessTests(APITestCase):
    """Test project access permissions"""
    
    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='Owner123!',
            role='PM'
        )
        self.member = CustomUser.objects.create_user(
            username='member',
            email='member@example.com',
            password='Member123!',
            role='DEV'
        )
        self.non_member = CustomUser.objects.create_user(
            username='nonmember',
            email='nonmember@example.com',
            password='NonMember123!',
            role='DEV'
        )
        
        # Create project
        self.project = Project.objects.create(
            name='Test Project',
            description='Test',
            owner=self.owner,
            status='IN_PROGRESS'
        )
        
        # Add member
        ProjectMember.objects.create(
            project=self.project,
            user=self.member,
            role='MEMBER'
        )
        
        self.project_detail_url = reverse('project-detail', kwargs={'slug': self.project.slug})
    
    def test_owner_can_view_project(self):
        """Test owner can view their project"""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(self.project_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_member_can_view_project(self):
        """Test member can view project"""
        self.client.force_authenticate(user=self.member)
        response = self.client.get(self.project_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_non_member_cannot_view_project(self):
        """Test non-member cannot view private project"""
        self.client.force_authenticate(user=self.non_member)
        response = self.client.get(self.project_detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_non_member_can_view_public_project(self):
        """Test non-member can view public project"""
        self.project.is_public = True
        self.project.save()
        
        self.client.force_authenticate(user=self.non_member)
        response = self.client.get(self.project_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_owner_can_update_project(self):
        """Test owner can update project"""
        self.client.force_authenticate(user=self.owner)
        data = {'name': 'Updated Project Name'}
        response = self.client.patch(self.project_detail_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, 'Updated Project Name')
    
    def test_member_cannot_update_project(self):
        """Test regular member cannot update project"""
        self.client.force_authenticate(user=self.member)
        data = {'name': 'Updated Project Name'}
        response = self.client.patch(self.project_detail_url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProjectMemberManagementTests(APITestCase):
    """Test project member management"""
    
    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            username='owner',
            email='owner@example.com',
            password='Owner123!',
            role='PM'
        )
        self.new_member = CustomUser.objects.create_user(
            username='newmember',
            email='newmember@example.com',
            password='Member123!',
            role='DEV'
        )
        self.non_owner = CustomUser.objects.create_user(
            username='nonowner',
            email='nonowner@example.com',
            password='NonOwner123!',
            role='DEV'
        )
        
        self.project = Project.objects.create(
            name='Test Project',
            description='Test',
            owner=self.owner,
            status='IN_PROGRESS'
        )
        
        self.add_member_url = reverse('project-add-member', kwargs={'slug': self.project.slug})
    
    def test_owner_can_add_member(self):
        """Test owner can add members"""
        self.client.force_authenticate(user=self.owner)
        data = {
            'user_id': self.new_member.id,
            'role': 'MEMBER'
        }
        response = self.client.post(self.add_member_url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ProjectMember.objects.filter(
                project=self.project,
                user=self.new_member
            ).exists()
        )
    
    def test_non_owner_cannot_add_member(self):
        """Test non-owner cannot add members"""
        self.client.force_authenticate(user=self.non_owner)
        data = {
            'user_id': self.new_member.id,
            'role': 'MEMBER'
        }
        response = self.client.post(self.add_member_url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProjectPaginationTests(APITestCase):
    """Test project pagination"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!',
            role='PM'
        )
        
        # Create 25 projects
        for i in range(1, 26):
            Project.objects.create(
                name=f'Project {i:02d}',
                description=f'Test project {i}',
                owner=self.user,
                status='PLANNING'
            )
        
        self.project_list_url = reverse('project-list')
    
    def test_default_pagination(self):
        """Test default pagination (15 per page)"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.project_list_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['projects']), 15)
        self.assertEqual(response.data['pagination']['total_pages'], 2)
        self.assertEqual(response.data['pagination']['count'], 25)
    
    def test_custom_page_size(self):
        """Test custom page size"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{self.project_list_url}?page_size=5')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['projects']), 5)
        self.assertEqual(response.data['pagination']['total_pages'], 5)
    
    def test_page_navigation(self):
        """Test navigating between pages"""
        self.client.force_authenticate(user=self.user)
        
        # Get page 1
        response = self.client.get(f'{self.project_list_url}?page=1')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data['pagination']['previous'])
        self.assertIsNotNone(response.data['pagination']['next'])
        
        # Get page 2
        response = self.client.get(f'{self.project_list_url}?page=2')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data['pagination']['previous'])
        self.assertIsNone(response.data['pagination']['next'])


class ProjectFilteringTests(APITestCase):
    """Test project filtering"""
    
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='Test123!',
            role='PM'
        )
        
        # Create projects with different statuses
        Project.objects.create(
            name='Planning Project',
            owner=self.user,
            status='PLANNING',
            priority='LOW'
        )
        Project.objects.create(
            name='Active Project',
            owner=self.user,
            status='IN_PROGRESS',
            priority='HIGH'
        )
        Project.objects.create(
            name='Completed Project',
            owner=self.user,
            status='COMPLETED',
            priority='MEDIUM'
        )
        
        self.project_list_url = reverse('project-list')
    
    def test_filter_by_status(self):
        """Test filtering projects by status"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{self.project_list_url}?status=IN_PROGRESS')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['pagination']['count'], 1)
        self.assertEqual(response.data['projects'][0]['status'], 'IN_PROGRESS')
    
    def test_filter_by_priority(self):
        """Test filtering projects by priority"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'{self.project_list_url}?priority=HIGH')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['pagination']['count'], 1)
        self.assertEqual(response.data['projects'][0]['priority'], 'HIGH')
    
    def test_search_projects(self):
        """Test searching projects by name - فقط پروژه‌های قابل دیدن کاربر"""
        self.client.force_authenticate(user=self.user)

        # ساخت یک پروژه کاملاً جدید با نام منحصر به فرد
        unique_name = "این_پروژه_فقط_برای_تست_سرچ_است_14031234"
        Project.objects.create(
            name=unique_name,
            owner=self.user,
            is_public=False,
            status='IN_PROGRESS'
        )

        # درخواست سرچ با دقیقاً همین نام
        response = self.client.get(f'{self.project_list_url}?search={unique_name}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # --- اصلاح شد: انتظار داریم فقط 1 مورد پیدا شود، نه کل پروژه‌ها ---
        self.assertEqual(response.data['pagination']['count'], 1) 
        # ---------------------------------------------------------------

        # بررسی اینکه آیا واقعا همانی است که ما ساختیم
        self.assertEqual(response.data['projects'][0]['name'], unique_name)

        # بخش دوم تست شما هم درست است (جستجو با بخشی از کلمه)
        response2 = self.client.get(f'{self.project_list_url}?search=14031234')
        self.assertEqual(response2.data['pagination']['count'], 1)
        self.assertEqual(response2.data['projects'][0]['name'], unique_name)
        
        