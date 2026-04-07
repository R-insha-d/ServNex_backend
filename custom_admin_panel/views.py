from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count
from hotels.models import HotelDataModel, Booking
from restaurants.models import RestaurantDataModel, TableReservation
from .serializers import (
    AdminUserSerializer, AdminHotelSerializer, 
    AdminRestaurantSerializer, AdminBookingSerializer,
    AdminReservationSerializer
)

User = get_user_model()

class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and (request.user.is_staff or request.user.is_superuser)

class GlobalStatsView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        total_users = User.objects.count()
        total_hotels = HotelDataModel.objects.count()
        total_restaurants = RestaurantDataModel.objects.count()
        
        # Calculate total revenue from hotel bookings (paid/confirmed)
        hotel_revenue = Booking.objects.filter(status__in=['confirmed', 'paid', 'completed']).aggregate(total=Sum('final_price'))['total'] or 0
        
        # Calculate total bookings
        hotel_bookings_count = Booking.objects.count()
        restaurant_reservations_count = TableReservation.objects.count()

        return Response({
            "total_users": total_users,
            "total_hotels": total_hotels,
            "total_restaurants": total_restaurants,
            "hotel_revenue": hotel_revenue,
            "total_bookings": hotel_bookings_count + restaurant_reservations_count,
            "hotel_bookings": hotel_bookings_count,
            "restaurant_reservations": restaurant_reservations_count,
        })

class AdminUserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-id')
    serializer_class = AdminUserSerializer
    permission_classes = [IsSuperAdmin]

class AdminHotelViewSet(viewsets.ModelViewSet):
    queryset = HotelDataModel.objects.all().order_by('-id')
    serializer_class = AdminHotelSerializer
    permission_classes = [IsSuperAdmin]

class AdminRestaurantViewSet(viewsets.ModelViewSet):
    queryset = RestaurantDataModel.objects.all().order_by('-id')
    serializer_class = AdminRestaurantSerializer
    permission_classes = [IsSuperAdmin]

class AdminBookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all().order_by('-id')
    serializer_class = AdminBookingSerializer
    permission_classes = [IsSuperAdmin]

class AdminReservationViewSet(viewsets.ModelViewSet):
    queryset = TableReservation.objects.all().order_by('-id')
    serializer_class = AdminReservationSerializer
    permission_classes = [IsSuperAdmin]
