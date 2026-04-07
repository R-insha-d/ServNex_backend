from rest_framework import serializers
from django.contrib.auth import get_user_model
from hotels.models import HotelDataModel, Booking
from restaurants.models import RestaurantDataModel, TableReservation

User = get_user_model()

class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'first_name', 'email', 'phone', 'role', 'is_active', 'is_staff', 'is_superuser', 'date_joined')
        read_only_fields = ('date_joined',)

class AdminHotelSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    class Meta:
        model = HotelDataModel
        fields = '__all__'

class AdminRestaurantSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    class Meta:
        model = RestaurantDataModel
        fields = '__all__'

class AdminBookingSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)
    class Meta:
        model = Booking
        fields = '__all__'

class AdminReservationSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    class Meta:
        model = TableReservation
        fields = '__all__'
