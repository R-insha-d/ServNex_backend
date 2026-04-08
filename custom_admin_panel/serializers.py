from rest_framework import serializers
from django.contrib.auth import get_user_model
from hotels.models import HotelDataModel, Booking, Review as HotelReview, Room
from restaurants.models import RestaurantDataModel, TableReservation, Review as RestaurantReview
from payments.models import Payment
from .models import AdminActivity

User = get_user_model()

class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'first_name', 'email', 'phone', 'role', 'is_active', 'is_staff', 'is_superuser', 'date_joined')
        read_only_fields = ('date_joined',)

class AdminRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = '__all__'
        extra_kwargs = {'hotel': {'required': False}} # Handled by nested logic

class AdminHotelSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    rooms = AdminRoomSerializer(many=True, required=False)

    class Meta:
        model = HotelDataModel
        fields = '__all__'

    def create(self, validated_data):
        rooms_data = validated_data.pop('rooms', [])
        hotel = HotelDataModel.objects.create(**validated_data)
        for room_data in rooms_data:
            Room.objects.create(hotel=hotel, **room_data)
        return hotel

    def update(self, instance, validated_data):
        rooms_data = validated_data.pop('rooms', [])
        instance = super().update(instance, validated_data)
        
        # Simple policy: replace rooms if provided
        if rooms_data:
            # We don't want to delete rooms blindly if they have bookings, 
            # but for this admin panel we'll allow replacing them.
            # A more robust sync logic could match by ID.
            instance.rooms.all().delete()
            for room_data in rooms_data:
                Room.objects.create(hotel=instance, **room_data)
        return instance

class AdminRestaurantSerializer(serializers.ModelSerializer):
    owner_email = serializers.SerializerMethodField()

    class Meta:
        model = RestaurantDataModel
        fields = '__all__'

    def get_owner_email(self, obj):
        return obj.owner.email if obj.owner else "No Owner"

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

# --- Enterprise Upgrade Serializers ---

class AdminPaymentSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    item_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = '__all__'

    def get_item_name(self, obj):
        # Resolve the generic foreign key object name
        if obj.content_object:
            if hasattr(obj.content_object, 'hotel'):
                return obj.content_object.hotel.name
            if hasattr(obj.content_object, 'restaurant'):
                return obj.content_object.restaurant.name
        return "Unknown Item"

class AdminHotelReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    hotel_name = serializers.CharField(source='hotel.name', read_only=True)

    class Meta:
        model = HotelReview
        fields = '__all__'

class AdminRestaurantReviewSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)

    class Meta:
        model = RestaurantReview
        fields = '__all__'

class AdminActivitySerializer(serializers.ModelSerializer):
    admin_name = serializers.CharField(source='admin_user.first_name', read_only=True)
    class Meta:
        model = AdminActivity
        fields = '__all__'
