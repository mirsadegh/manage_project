# manage_project

Brief description of your Django project.

## Setup

1. Clone the repository
```bash

git clone https://github.com/mirsadegh/manage_project.git
cd manage_project
```

2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Set up environment variables
```bash
cp .env.example .env
# Edit .env with your settings
```

5. Run migrations
```bash
python manage.py migrate
```

6. Create superuser
```bash
python manage.py createsuperuser
```

7. Run development server
```bash
python manage.py runserver
```

## Technologies Used

- Django
- PostgreSQL
- Django REST Framework
- Celery
- Redis
- Docker


- [Other technologies]
 ---

 Database Relationships Diagram

 CustomUser ───┬──► Project (owner)
               ├──► Project (manager)
               ├──► ProjectMember
               ├──► Task (assignee)
               ├──► Task (created_by)
               ├──► Comment (author)
               ├──► Attachment (uploaded_by)
               ├──► Notification (recipient)
               ├──► ActivityLog (user)
               └──► Team (via TeamMembership)

 Project ───┬──► ProjectMember
            ├──► Task
            ├──► TaskList
            └──► TaskLabel

 Task ───┬──► TaskLabelAssignment
         ├──► TaskDependency
         ├──► Comment (via GenericForeignKey)
         ├──► Attachment (via GenericForeignKey)
         └──► Subtasks (self-referential)

 TaskList ───► Task

 Team ───► TeamMembership ───► CustomUser


 Summary of Models
 App          Models                  Purpose
 accounts     CustomUserUser          authentication and 
 profiles
 projects     Project, ProjectMember   Project management and 
 team
 tasks        (Task, TaskList, TaskLabel, 
 TaskLabelAssignment, TaskDependency )     Task management
 teams        Team, TeamMembership        Team organization 
 comments     Comment          Discussions and feedback
 files        Attachment      File uploads
 notifications  Notification   User notifications
 activity      ActivityLog     Audit trail and history



 API Endpoint Summary
📁 File Upload Endpoints
MethodEndpointDescriptionAuth Required🟢 GET/api/files/
attachments/List all attachments✅ Yes🟢 GET/api/files/
attachments/?content_type=task&object_id=1Filter by object✅ 
Yes🔵 POST/api/files/attachments/Upload file✅ Yes🟢 GET/api/
files/attachments/{id}/Get file details✅ Yes🟢 GET/api/files/
attachments/{id}/download/Download file✅ Yes🟢 GET/api/files/
attachments/{id}/preview/Preview file✅ Yes🔴 DELETE/api/files/
attachments/{id}/Delete file✅ Yes🟢 GET/api/files/attachments/
stats/Get upload stats✅ Yes
💬 Comment Endpoints
MethodEndpointDescriptionAuth Required🟢 GET/api/comments/
comments/List comments✅ Yes🟢 GET/api/comments/comments/?
content_type=task&object_id=1Filter comments✅ Yes🔵 POST/api/
comments/comments/Create comment✅ Yes🟡 PUT/api/comments/
comments/{id}/Update comment✅ Yes🔴 DELETE/api/comments/
comments/{id}/Delete comment✅ Yes🔵 POST/api/comments/
comments/{id}/react/Add reaction✅ Yes🔴 DELETE/api/comments/
comments/{id}/unreact/Remove reaction✅ Yes
📋 Task Comment Shortcuts
MethodEndpointDescription🟢 GET/api/tasks/tasks/{id}/comments/
Get task comments🔵 POST/api/tasks/tasks/{id}/add_comment/Add 
comment to task🟢 GET/api/tasks/tasks/{id}/attachments/Get 
task files🔵 POST/api/tasks/tasks/{id}/upload_file/Upload 
file to task




