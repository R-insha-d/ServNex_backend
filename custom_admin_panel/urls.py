from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AdminUserViewSet, AdminHotelViewSet, 
    AdminRestaurantViewSet, AdminBookingViewSet,
    AdminReservationViewSet, AdminPaymentViewSet,
    AdminHotelReviewViewSet, AdminRestaurantReviewViewSet,
    AdminActivityViewSet,
    GlobalStatsView, AdminAnalyticsView
)

router = DefaultRouter()
router.register(r'users', AdminUserViewSet, basename='admin-users')
router.register(r'hotels', AdminHotelViewSet, basename='admin-hotels')
router.register(r'restaurants', AdminRestaurantViewSet, basename='admin-restaurants')
router.register(r'bookings', AdminBookingViewSet, basename='admin-bookings')
router.register(r'reservations', AdminReservationViewSet, basename='admin-reservations')
router.register(r'payments', AdminPaymentViewSet, basename='admin-payments')
router.register(r'activity', AdminActivityViewSet, basename='admin-activity')
router.register(r'hotel-reviews', AdminHotelReviewViewSet, basename='admin-hotel-reviews')
router.register(r'restaurant-reviews', AdminRestaurantReviewViewSet, basename='admin-restaurant-reviews')

urlpatterns = [
    path('', include(router.urls)),
    path('stats/', GlobalStatsView.as_view(), name='admin-stats'),
    path('analytics/', AdminAnalyticsView.as_view(), name='admin-analytics'),
]
