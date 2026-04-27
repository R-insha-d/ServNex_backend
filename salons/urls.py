from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SalonViewSet, SalonServiceViewSet, SalonQueueEntryViewSet, 
    SalonDashboardQueueView, SalonDashboardRecordsView, ReviewViewSet,
    SalonGalleryView, SalonGalleryDeleteView
)

router = DefaultRouter()
router.register(r'salons', SalonViewSet, basename='salon')
router.register(r'salon-services', SalonServiceViewSet, basename='salon-service')
router.register(r'queue', SalonQueueEntryViewSet, basename='salon-queue')
router.register(r'salon-reviews', ReviewViewSet, basename='salon-review')

urlpatterns = [
    path('', include(router.urls)),
    # Dashboard specific endpoints
    path('salon-dashboard/queue/', SalonDashboardQueueView.as_view(), name='salon-dashboard-queue'),
    path('salon-dashboard/previous-records/', SalonDashboardRecordsView.as_view(), name='salon-dashboard-records'),
    # Gallery management
    path('salon-dashboard/gallery/', SalonGalleryView.as_view(), name='salon-gallery-list'),
    path('salon-dashboard/gallery/<int:pk>/delete/', SalonGalleryDeleteView.as_view(), name='salon-gallery-delete'),
]
