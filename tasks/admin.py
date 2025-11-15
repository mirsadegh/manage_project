from django.contrib import admin
from .models import  Task, TaskList, TaskLabel
# Register your models here.

admin.site.register(Task)
admin.site.register(TaskList)
admin.site.register(TaskLabel)


