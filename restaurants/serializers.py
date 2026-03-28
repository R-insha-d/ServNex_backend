from django.db import models as db_models
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import RestaurantDataModel, TableReservation, Review, ReviewImage


class RestaurantSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.get_full_name', read_only=True)
    image = serializers.ImageField(required=False)
    menu_image = serializers.ImageField(required=False)
    interior_image = serializers.ImageField(required=False)

    class Meta:
        model = RestaurantDataModel
        fields = [
            'id', 'owner', 'owner_name', 'name', 'city', 'area', 'badge',
            'cuisine_type', 'price_range', 'average_cost_for_two', 
            'tables_4_capacity', 'tables_6_capacity', 'tables_8_capacity', 'tables_10_capacity',
            'total_tables', 'description', 'rating', 'image', 'menu_image', 'interior_image',
            'latitude', 'longitude', 'keywords', 'is_open', 'opening_time', 'closing_time',
            'created_at', 'updated_at', 'reviews_count', 'average_rating',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'owner', 'owner_name', 'reviews_count', 'average_rating', 'total_tables']

    reviews_count = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    def get_reviews_count(self, obj):
        return obj.reviews.count()

    def get_average_rating(self, obj):
        ratings = obj.reviews.values_list('rating', flat=True)
        if not ratings:
            return float(obj.rating) if obj.rating else 0.0
        return round(sum(ratings) / len(ratings), 1)

    def update(self, instance, validated_data):
        # Prevent deleting images if not sent
        for field in ['image', 'menu_image', 'interior_image']:
            if field not in validated_data:
                validated_data[field] = getattr(instance, field)
        return super().update(instance, validated_data)
    

class ReviewImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewImage
        fields = ['id', 'image', 'created_at']

class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.first_name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    images = ReviewImageSerializer(many=True, read_only=True)

    class Meta:
        model = Review
        fields = [
            'id', 'reservation', 'restaurant', 'user', 'user_name',
            'user_email', 'rating', 'comment', 'created_at', 'images'
        ]
        read_only_fields = ['id', 'created_at', 'user', 'user_name', 'user_email', 'restaurant']

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate(self, data):
        reservation = data.get('reservation')
        restaurant = data.get('restaurant')
        reservation_time = data.get('reservation_time')
        
        if restaurant and reservation_time:
            # Check if restaurant is explicitly closed
            if hasattr(restaurant, 'is_open') and not restaurant.is_open:
                raise serializers.ValidationError("This restaurant is currently closed for reservations.")
            
            # Check operating hours
            if hasattr(restaurant, 'opening_time') and hasattr(restaurant, 'closing_time'):
                opening = restaurant.opening_time
                closing = restaurant.closing_time
                
                if not (opening <= reservation_time <= closing):
                    raise serializers.ValidationError(
                        f"Reservation time must be between {opening.strftime('%I:%M %p')} and {closing.strftime('%I:%M %p')}."
                    )

        # Only allow review if reservation is completed
        if reservation and reservation.status not in ['Your Table Is Ready', 'completed', 'paid']:
            raise serializers.ValidationError("You can only review a confirmed or completed reservation.")
        # One review per reservation (only check on creation)
        if not self.instance and reservation and Review.objects.filter(reservation=reservation).exists():
            raise serializers.ValidationError("You have already reviewed this reservation.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        reservation = validated_data['reservation']
        images_data = request.FILES.getlist('images')

        validated_data['user'] = request.user
        validated_data['restaurant'] = reservation.restaurant
        review = super().create(validated_data)

        for image_data in images_data:
            ReviewImage.objects.create(review=review, image=image_data)
        return review


class TableReservationSerializer(serializers.ModelSerializer):
    restaurant_name = serializers.CharField(source='restaurant.name', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    restaurant_image = serializers.ImageField(source='restaurant.image', read_only=True)
    menu_image = serializers.ImageField(source='restaurant.menu_image', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    has_review = serializers.SerializerMethodField()
    review_data = serializers.SerializerMethodField()

    payment_info = serializers.SerializerMethodField()

    class Meta:
        model = TableReservation
        fields = [
            'id', 'user', 'user_name', 'user_email', 'user_phone',
            'restaurant', 'restaurant_name', 'restaurant_image', 'menu_image',
            'reservation_date', 'reservation_time',
            'number_of_guests', 'tables_reserved', 'status', 'special_requests',
            'razorpay_order_id', 'payment_status',
            'has_review', 'review_data', 'payment_info',
            'created_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'user', 'user_name', 'restaurant_name',
            'restaurant_image', 'menu_image', 'tables_reserved',
            'razorpay_order_id', 'payment_status',
            'has_review', 'review_data'
        ]

    def get_payment_info(self, obj):
        if obj.razorpay_order_id:
            from payments.models import Payment
            p = Payment.objects.filter(razorpay_order_id=obj.razorpay_order_id).first()
            if p:
                return {
                    'amount': str(p.amount),
                    'transaction_id': p.razorpay_payment_id or '—',
                    'currency': p.currency,
                }
        return None

    def get_has_review(self, obj):
        """Returns True if this reservation already has a review"""
        return hasattr(obj, 'review')

    def get_review_data(self, obj):
        """Returns review details if exists, else None"""
        if hasattr(obj, 'review'):
            return {
                'id': obj.review.id,
                'rating': obj.review.rating,
                'comment': obj.review.comment,
                'created_at': obj.review.created_at,
                'images': ReviewImageSerializer(obj.review.images.all(), many=True).data
            }
        return None

    def validate(self, data):
        from datetime import date

        # Check reservation date is not in the past
        # [RELAXED] Skip this check if we are CANCELLING the reservation
        status = data.get('status')
        if status != 'cancelled' and data.get('reservation_date') and data['reservation_date'] < date.today():
            raise serializers.ValidationError("Reservation date cannot be in the past.")

        # Operating hours check
        restaurant = data.get('restaurant')
        reservation_time = data.get('reservation_time')
        if restaurant and reservation_time:
            if not (restaurant.opening_time <= reservation_time <= restaurant.closing_time):
                raise serializers.ValidationError(
                    f"The restaurant is only open between {restaurant.opening_time.strftime('%I:%M %p')} and {restaurant.closing_time.strftime('%I:%M %p')}. Please select a valid time."
                )

        # Table availability check based on capacity
        reservation_date = data.get('reservation_date')
        guests = data.get('number_of_guests', 1)
        
        # Determine capacity type
        if guests <= 4: capacity = 4
        elif guests <= 6: capacity = 6
        elif guests <= 8: capacity = 8
        else: capacity = 10

        if status != 'cancelled' and restaurant and reservation_date:
            # Check how many tables of THIS capacity are already booked for this date
            qs = TableReservation.objects.filter(
                restaurant=restaurant,
                reservation_date=reservation_date,
                table_capacity=capacity
            ).filter(
                Q(payment_status='paid') | Q(status__in=['Your Table Is Ready', 'completed'])
            ).exclude(status='cancelled')
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)

            already_booked = qs.count() # Each record is 1 table now

            # Get total allowed for this capacity
            field_name = f'tables_{capacity}_capacity'
            total_allowed = getattr(restaurant, field_name, 0)
            
            available = total_allowed - already_booked

            if available <= 0:
                raise serializers.ValidationError(
                    f"Sorry, no {capacity}-guest tables are available for this date. Please try another table type or date."
                )

        return data