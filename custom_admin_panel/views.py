from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth, TruncDay
from django.utils import timezone
import datetime
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
        days = int(request.query_params.get('days', 30))
        now = timezone.now()
        start_date = now - datetime.timedelta(days=days)
        prev_start = start_date - datetime.timedelta(days=days)

        # Baseline stats
        total_users = User.objects.count()
        total_hotels = HotelDataModel.objects.count()
        total_restaurants = RestaurantDataModel.objects.count()
        hotel_revenue = Booking.objects.filter(status__in=['confirmed', 'paid', 'completed']).aggregate(total=Sum('final_price'))['total'] or 0
        hotel_bookings_count = Booking.objects.count()
        restaurant_reservations_count = TableReservation.objects.count()

        # Growth calculation helper
        def get_growth(queryset, date_field='created_at'):
            current = queryset.filter(**{f"{date_field}__range": (start_date, now)}).count()
            previous = queryset.filter(**{f"{date_field}__range": (prev_start, start_date)}).count()
            if previous == 0:
                return 100 if current > 0 else 0
            return round(((current - previous) / previous) * 100, 1)

        return Response({
            "total_users": total_users,
            "total_hotels": total_hotels,
            "total_restaurants": total_restaurants,
            "hotel_revenue": hotel_revenue,
            "total_bookings": hotel_bookings_count + restaurant_reservations_count,
            "hotel_bookings": hotel_bookings_count,
            "restaurant_reservations": restaurant_reservations_count,
            
            # Trends
            "user_growth": get_growth(User.objects.all(), 'date_joined'),
            "revenue_growth": get_growth(Booking.objects.filter(status__in=['confirmed', 'paid', 'completed'])),
            "booking_growth": get_growth(Booking.objects.all()),
            "partner_growth": 0 # Native models lack registration timestamps
        })

class AdminAnalyticsView(APIView):
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        days = int(request.query_params.get('days', 180))
        start_date = timezone.now() - datetime.timedelta(days=days)
        
        # Adaptive granularity (Daily for <= 30 days, Monthly for longer)
        trunc_func = TruncDay if days <= 30 else TruncMonth

        # Revenue Trends
        revenue_data = Booking.objects.filter(
            status__in=['confirmed', 'paid', 'completed'],
            created_at__gte=start_date
        ).annotate(period=trunc_func('created_at')).values('period').annotate(
            total=Sum('final_price')
        ).order_by('period')

        # New Users
        user_data = User.objects.filter(
            date_joined__gte=start_date
        ).annotate(period=trunc_func('date_joined')).values('period').annotate(
            count=Count('id')
        ).order_by('period')

        return Response({
            "revenue_trends": list(revenue_data),
            "user_growth": list(user_data),
            "distribution": {
                "hotels": HotelDataModel.objects.count(),
                "restaurants": RestaurantDataModel.objects.count()
            }
        })

class AdminUserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-id')
    serializer_class = AdminUserSerializer
    permission_classes = [IsSuperAdmin]
    filterset_fields = ['role', 'is_active', 'is_staff']
    search_fields = ['first_name', 'email', 'phone']
    ordering_fields = ['id', 'date_joined', 'first_name']

class AdminHotelViewSet(viewsets.ModelViewSet):
    queryset = HotelDataModel.objects.all().order_by('-id')
    serializer_class = AdminHotelSerializer
    permission_classes = [IsSuperAdmin]
    filterset_fields = ['badge', 'city', 'area']
    search_fields = ['name', 'city', 'area', 'description']
    ordering_fields = ['id', 'name', 'price']

class AdminRestaurantViewSet(viewsets.ModelViewSet):
    queryset = RestaurantDataModel.objects.all().order_by('-id')
    serializer_class = AdminRestaurantSerializer
    permission_classes = [IsSuperAdmin]
    filterset_fields = ['cuisine_type', 'city', 'price_range']
    search_fields = ['name', 'city', 'area']
    ordering_fields = ['id', 'name', 'rating']

class AdminBookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all().order_by('-id')
    serializer_class = AdminBookingSerializer
    permission_classes = [IsSuperAdmin]
    filterset_fields = ['status', 'payment_status']
    search_fields = ['id', 'user__email', 'hotel__name']
    ordering_fields = ['id', 'created_at', 'final_price']

class AdminReservationViewSet(viewsets.ModelViewSet):
    queryset = TableReservation.objects.all().order_by('-id')
    serializer_class = AdminReservationSerializer
    permission_classes = [IsSuperAdmin]
    filterset_fields = ['status']
    search_fields = ['id', 'user__email', 'restaurant__name']
    ordering_fields = ['id', 'created_at']
