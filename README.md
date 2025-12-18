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
MethodEndpointDescriptionAuth Required
🟢 GET  /api/files/attachments/List all attachments  ✅ Yes
🟢 GET  /api/files/attachments/?content_type=task&object_id=1Filter by object ✅ Yes
🔵 POST/api/files/attachments/Upload file✅ Yes
🟢 GET/api/files/attachments/{id}/Get file details✅ Yes🟢 GET/api/files/
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


API Endpoint Summary
📋 Complete Team Endpoints
Method  Endpoint                    Description                     🔐  Auth
Teams 
🟢GET      /api/teams/teams/          List all teams                 ✅
🔵POST    /api/teams/teams/           Create team                    ✅ 
🟢GET    /api/teams/teams/{slug}/     Get team details               ✅ 
🟡PATCH  /api/teams/teams/{slug}/     Update team                    ✅
🔴DELETE  /api/teams/teams/{slug}/    Delete team                    ✅
🟢GET     /api/teams/teams/my_teams/  Get user's teams               ✅         
Members
🔵POST     /api/teams/teams/{slug}/add_member/  Add member   ✅                     
🔴DELETE   /api/teams/teams/{slug}/remove_member/{id}/ Remove member  ✅
🔵POST      /api/teams/teams/{slug}/join/   Join team      ✅

Invitations
🔵 POST   /api/teams/teams/{slug}/invite/Send invitation     ✅
🟢 GET    /api/teams/team-invitations/List invitations          ✅
🔵 POST   /api/teams/team-invitations/{id}/accept/Accept invitation     ✅
🔵 POST    /api/teams/team-invitations/{id}/decline/Decline invitation   ✅

Projects
🟢 GET/api/teams/teams/{slug}/projects/Get team projects✅
🔵 POST/api/teams/teams/{slug}/assign_project/Assign project✅
Meetings
🟢 GET/api/teams/teams/{slug}/meetings/Get meetings✅
🔵 POST/api/teams/teams/{slug}/schedule_meeting/Schedule meeting✅
🔵 POST/api/teams/team-meetings/{id}/complete/Complete meeting✅
Goals
🟢 GET/api/teams/teams/{slug}/goals/Get team goals✅
🔵 POST/api/teams/teams/{slug}/create_goal/Create goal✅
🔵 POST/api/teams/team-goals/{id}/update_progress/Update progress✅
Performance
🟢 GET/api/teams/teams/{slug}/performance/Get performance report✅

Complete Testing✅ 
Run All Tests
bash# 🧪 Run all team tests
python manage.py test teams --verbosity=2

# 📊 Generate coverage report
coverage run --source='teams' manage.py test teams
coverage report
coverage html

# 🌐 Open coverage report
open htmlcov/index.html

🎉 10. Summary - Complete Team Management
✨ What's Been Built
👥 Team Management

✅ Create and manage teams
✅ Multiple team types (Dev, Design, Marketing, etc.)
✅ Team leaders and co-leaders
✅ Member roles and performance tracking
✅ Self-join or invitation-only teams
✅ Maximum member limits

📨 Invitation System

✅ Send team invitations
✅ Accept/decline invitations
✅ Auto-expiration (7 days)
✅ Email notifications

📊 Project Assignment

✅ Assign teams to projects
✅ Primary team designation
✅ Track project completion rates

📅 Meeting Management

✅ Schedule team meetings
✅ Multiple meeting types (Standup, Weekly, Planning, etc.)
✅ Meeting reminders (1 hour before)
✅ Meeting notes and action items

🎯 Goal Tracking

✅ Set team goals
✅ Track progress (0-100%)
✅ Target dates and metrics
✅ Overdue detection

📈 Performance Metrics

✅ Team completion rates
✅ Member performance ratings
✅ Active projects/tasks tracking
✅ Performance reports

⚡ Automation

✅ Auto-expire old invitations (daily)
✅ Meeting reminders (hourly)
✅ Team stats updates (weekly)

🚀 Ready to Use!
Your team management system is now complete and production-ready! 🎊
Would you like me to add:

📱 Mobile App Integration
📊 Advanced Analytics Dashboard
🔔 Real-time Notifications
🌍 Internationalization (i18n)
🎨 Custom Themes