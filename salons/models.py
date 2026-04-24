from django.db import models
from django.contrib.auth import get_user_model

# Get the user model
User = get_user_model()

class SalonDataModel(models.Model):
    BADGE_CHOICES = [
        ('Premium Saloon', 'Premium Saloon'),
        ('Budget Friendly', 'Budget Friendly'),
        ('Spa & Wellness', 'Spa & Wellness'),
        ('Unisex', 'Unisex'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='salons', null=True, blank=True)
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    area = models.CharField(max_length=500)
    address = models.CharField(max_length=500, null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    badge = models.CharField(max_length=50, choices=BADGE_CHOICES, null=True, blank=True)
    image = models.ImageField(upload_to='salons/', null=True, blank=True)
    amenities = models.TextField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)    
    keywords = models.TextField(null=True, blank=True, help_text="Keywords for search optimization (comma separated)")
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True, default=0.0)
    is_open = models.BooleanField(default=True)
    opening_time = models.TimeField(default="09:00:00")
    closing_time = models.TimeField(default="21:00:00")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.latitude or not self.longitude:
            try:
                from search.utils import geocode_address
                address = f"{self.area}, {self.city}"
                lat, lng = geocode_address(address)
                if lat and lng:
                    self.latitude = lat
                    self.longitude = lng
            except Exception as e:
                print(f"Geocoding failed for {self.name}: {e}")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class SalonService(models.Model):
    salon = models.ForeignKey(SalonDataModel, on_delete=models.CASCADE, related_name='services')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration = models.CharField(max_length=50, help_text="e.g., 30 mins")

    def __str__(self):
        return f"{self.name} - {self.salon.name}"

class SalonQueueEntry(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='salon_queues', null=True, blank=True)
    guest_name = models.CharField(max_length=255, null=True, blank=True)
    guest_phone = models.CharField(max_length=20, null=True, blank=True)
    salon = models.ForeignKey(SalonDataModel, on_delete=models.CASCADE, related_name='queue_entries')
    service = models.ForeignKey(SalonService, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    joined_at = models.DateTimeField(auto_now_add=True)
    estimated_wait_time = models.PositiveIntegerField(default=0, help_text="Estimated wait time in minutes")

    class Meta:
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.user} @ {self.salon.name} - {self.status}"

class Review(models.Model):
    queue_entry = models.OneToOneField(
        SalonQueueEntry,
        on_delete=models.CASCADE,
        related_name='review',
        null=True, # allow null temporarily for existing data or if needed
        blank=True
    )
    salon = models.ForeignKey(SalonDataModel, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='salon_reviews')
    rating = models.PositiveSmallIntegerField(default=5)
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} → {self.salon.name} ({self.rating}⭐)"

class ReviewImage(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='salon_review_photos/')
    created_at = models.DateTimeField(auto_now_add=True)

class SalonGallery(models.Model):
    salon = models.ForeignKey(SalonDataModel, on_delete=models.CASCADE, related_name='gallery')
    image = models.ImageField(upload_to='salons/gallery/')

    def __str__(self):
        return f"Gallery Image for {self.salon.name}"
