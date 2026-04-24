from django.contrib import admin
from .models import SalonDataModel, SalonService, SalonQueueEntry, Review, ReviewImage, SalonGallery


@admin.register(SalonDataModel)
class SalonAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'area', 'is_open', 'badge', 'owner']
    list_filter = ['is_open', 'badge', 'city']
    search_fields = ['name', 'city', 'area']


@admin.register(SalonService)
class SalonServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'salon', 'price', 'duration']
    search_fields = ['name', 'salon__name']


@admin.register(SalonQueueEntry)
class SalonQueueEntryAdmin(admin.ModelAdmin):
    list_display = ['user', 'salon', 'service', 'status', 'joined_at']
    list_filter = ['status']
    search_fields = ['user__email', 'salon__name']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['user', 'salon', 'rating', 'created_at']
    list_filter = ['rating']


@admin.register(ReviewImage)
class ReviewImageAdmin(admin.ModelAdmin):
    list_display = ['review', 'created_at']


@admin.register(SalonGallery)
class SalonGalleryAdmin(admin.ModelAdmin):
    list_display = ['salon', 'image']
    search_fields = ['salon__name']
