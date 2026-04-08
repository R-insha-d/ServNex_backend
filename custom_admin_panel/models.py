from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class AdminActivity(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated'),
        ('DELETE', 'Deleted'),
        ('OTHER', 'Other Action'),
    ]

    admin_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_actions')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50, null=True, blank=True)
    object_repr = models.CharField(max_length=255, help_text="Human readable representation of the object")
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Store the changes if possible (optional but high quality)
    changes = models.JSONField(null=True, blank=True, help_text="Detailed changes in JSON format")

    class Meta:
        verbose_name_plural = "Admin Activities"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.admin_user.first_name} {self.action} {self.model_name}: {self.object_repr}"
