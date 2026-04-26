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
    distance = serializers.SerializerMethodField()

    class Meta:
        model = RestaurantDataModel
        fields = [
            'id', 'owner', 'owner_name', 'name', 'city', 'area', 'badge',
            'cuisine_type', 'price_range', 'average_cost_for_two',
            'tables_2_capacity', 
            'tables_4_capacity', 'tables_6_capacity', 'tables_8_capacity', 'tables_10_capacity',
            'total_tables', 'description', 'rating', 'image', 'menu_image', 'interior_image','extra_image',
            'latitude', 'longitude', 'keywords', 'is_open', 'opening_time', 'closing_time',
            'created_at', 'updated_at', 'reviews_count', 'average_rating', 'distance',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'owner', 'owner_name', 'reviews_count', 'average_rating', 'total_tables']

    reviews_count = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()

    def get_distance(self, obj):
        return getattr(obj, 'distance', None)

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
            'user_email', 'rating', 'comment', 'created_at', 'images',
        ]
        read_only_fields = ['id', 'created_at', 'user', 'user_name', 'user_email', 'restaurant']

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate(self, data):

        restaurant = data.get('restaurant')
        reservation_date = data.get('reservation_date')
        table_selection = data.get('table_selection', {})

        if not table_selection:
            raise serializers.ValidationError("Please select at least one table.")

        total_seats = 0

        for cap, count in table_selection.items():
            cap = int(cap)
            count = int(count)

            if count <= 0:
                continue

        total_seats += cap * count

        # 🔍 Check availability per type
        qs = TableReservation.objects.filter(
            restaurant=restaurant,
            reservation_date=reservation_date
        ).filter(
            Q(payment_status='paid') | Q(status__in=['Your Table Is Ready', 'completed'])
        ).exclude(status='cancelled')

        already_booked = 0

        for res in qs:
            sel = res.table_selection or {}
            already_booked += int(sel.get(str(cap), 0))

        total_allowed = getattr(restaurant, f"tables_{cap}_capacity", 0)
        available = total_allowed - already_booked

        if count > available:
            raise serializers.ValidationError(
                f"Only {available} tables available for {cap}-seater."
            )

    # 🚫 LIMIT CHECK
        if total_seats > 30:
         raise serializers.ValidationError("You can only select up to 30 seats.")

        data['total_seats'] = total_seats
        data['number_of_guests'] = total_seats  # fallback compatibility

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

    restaurant_area = serializers.CharField(source="restaurant.area", read_only=True)
    restaurant_city = serializers.CharField(source="restaurant.city", read_only=True)

    payment_info = serializers.SerializerMethodField()

    class Meta:
        model = TableReservation
        fields = [
            'id', 'user', 'user_name', 'user_email', 'user_phone',
            'restaurant', 'restaurant_name', 'restaurant_image', 'menu_image',
            'restaurant_area', 'restaurant_city',
            'reservation_date', 'reservation_time',
            'number_of_guests', 'table_capacity', 'tables_reserved', 'status', 'special_requests',
            'razorpay_order_id', 'payment_status',
            'has_review', 'review_data', 'payment_info','table_selection',
            'total_seats',
            'has_baby',
            'created_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'user', 'user_name', 'restaurant_name',
            'restaurant_image', 'menu_image',
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
        from datetime import datetime, date as date_obj, time as time_obj, timedelta
        from django.utils import timezone

    # Check reservation date and time are not in the past
        status = data.get('status')
        res_date = data.get('reservation_date')
        res_time = data.get('reservation_time')
    
        if status != 'cancelled' and res_date and res_time:
            res_datetime = timezone.make_aware(datetime.combine(res_date, res_time))
            if res_datetime < (timezone.now() - timedelta(minutes=1)):
                raise serializers.ValidationError("Reservation date and time cannot be in the past.")

    # Operating hours check
        restaurant = data.get('restaurant')
        reservation_time = data.get('reservation_time')
        if restaurant and reservation_time:
            if not (restaurant.opening_time <= reservation_time <= restaurant.closing_time):
                raise serializers.ValidationError(
                f"The restaurant is only open between {restaurant.opening_time.strftime('%I:%M %p')} and {restaurant.closing_time.strftime('%I:%M %p')}. Please select a valid time."
            )

    # ✅ NEW: Multi-table validation logic
        reservation_date = data.get('reservation_date')
        table_selection = data.get('table_selection', {})
    
        if table_selection and status != 'cancelled' and restaurant and reservation_date:
            total_seats = 0

            for cap_str, count in table_selection.items():
                cap = int(cap_str)
                count = int(count)

                if count <= 0:
                    continue

                total_seats += cap * count

            # Check availability for THIS specific table type
                qs = TableReservation.objects.filter(
                    restaurant=restaurant,
                    reservation_date=reservation_date
                ).filter(
                    Q(payment_status='paid') | Q(status__in=['Your Table Is Ready', 'completed'])
                ).exclude(status='cancelled')
            
            # Exclude current instance if updating
                if self.instance:
                    qs = qs.exclude(pk=self.instance.pk)

            # Count how many of THIS capacity are already booked
                already_booked = 0
                for res in qs:
                    sel = res.table_selection or {}
                    already_booked += int(sel.get(str(cap), 0))

            # Get total allowed for this capacity
                total_allowed = getattr(restaurant, f"tables_{cap}_capacity", 0)
                available = total_allowed - already_booked

                if count > available:
                    raise serializers.ValidationError(
                    f"Only {available} tables available for {cap}-seater on this date."
                )

        # Check 30-seat limit
            if total_seats > 30:
                raise serializers.ValidationError("You can only select up to 30 seats in total.")

        # Update the total seats and guest count
            data['total_seats'] = total_seats
            data['number_of_guests'] = total_seats

        return data