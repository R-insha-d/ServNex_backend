from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AdminUserViewSet, AdminHotelViewSet, 
    AdminRestaurantViewSet, AdminBookingViewSet,
    AdminReservationViewSet, GlobalStatsView,
    AdminAnalyticsView
)

router = DefaultRouter()
router.register(r'users', AdminUserViewSet, basename='admin-users')
router.register(r'hotels', AdminHotelViewSet, basename='admin-hotels')
router.register(r'restaurants', AdminRestaurantViewSet, basename='admin-restaurants')
router.register(r'bookings', AdminBookingViewSet, basename='admin-bookings')
router.register(r'reservations', AdminReservationViewSet, basename='admin-reservations')

urlpatterns = [
    path('', include(router.urls)),
    path('stats/', GlobalStatsView.as_view(), name='admin-stats'),
    path('analytics/', AdminAnalyticsView.as_view(), name='admin-analytics'),
]
