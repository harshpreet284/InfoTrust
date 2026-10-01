from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'user', 'target', 'timestamp')
    list_filter = ('action', 'timestamp')
    search_fields = ('action', 'target', 'user__email', 'id')
    readonly_fields = ('id', 'user', 'action', 'target', 'metadata', 'timestamp')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
