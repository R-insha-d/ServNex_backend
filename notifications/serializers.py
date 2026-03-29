from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    created_at_human = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'title', 'message', 'notification_type', 
            'link', 'is_read', 'created_at', 'created_at_human'
        ]
        read_only_fields = ['user', 'created_at']

    def get_created_at_human(self, obj):
        from django.utils import timezone
        import datetime
        
        now = timezone.now()
        diff = now - obj.created_at

        if diff.days > 0:
            return f"{diff.days}d ago"
        seconds = diff.seconds
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        return f"{seconds // 3600}h ago"
