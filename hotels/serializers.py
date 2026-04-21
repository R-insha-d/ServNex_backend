from rest_framework import serializers
from .models import HotelDataModel, Booking, Room, HotelGallery, NearbyAttraction, Review, Coupon, ReviewImage 
from django.contrib.auth import get_user_model
from django.db.models import Q, Sum

User = get_user_model()


class HotelCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HotelDataModel
        fields = [
            'name', 'city', 'area', 'badge',
            'price', 'old_price', 'description','amenities', 'image', 
            'room_image1', 'room_image2', 'environment_image',
            'latitude', 'longitude', 'keywords'
        ]

    def create(self, validated_data):
        user = self.context['request'].user
        return HotelDataModel.objects.create(owner=user, **validated_data)

class NearbyAttractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = NearbyAttraction
        fields = ["id", "hotel", "name", "distance_km"]

    def validate(self, data):
        hotel = data.get('hotel')
        # Check limit only for new creations
        if not self.instance and hotel:
            if NearbyAttraction.objects.filter(hotel=hotel).count() >= 5:
                raise serializers.ValidationError("You can only add up to 5 nearby places.")
        return data


class HotelListSerializer(serializers.ModelSerializer):
    owner = serializers.CharField(source="owner.username", read_only=True)
    amenities = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    room_image1 = serializers.SerializerMethodField()
    room_image2 = serializers.SerializerMethodField()
    environment_image = serializers.SerializerMethodField()
    nearby_attractions = NearbyAttractionSerializer(many=True, read_only=True)
    average_rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()


    class Meta:
        model = HotelDataModel
        fields = [
            'id',
            'owner',
            'name',
            'city',
            'area',
            'badge',
            'price',
            'old_price',
            'description',
            'amenities',
            'image',
            'room_image1',
            'room_image2',
            'environment_image',
            'nearby_attractions',
            'average_rating',
            'reviews_count',
            'latitude',
            'longitude',
            'keywords',
        ]
    
    def get_amenities(self, obj):
        if obj.amenities:
            # Split by comma and strip whitespace
            return [a.strip() for a in obj.amenities.split(',') if a.strip()]
        return []

    def get_image(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

    def get_room_image1(self, obj):
        request = self.context.get("request")
        if obj.room_image1 and request:
            return request.build_absolute_uri(obj.room_image1.url)
        return None

    def get_room_image2(self, obj):
        request = self.context.get("request")
        if obj.room_image2 and request:
            return request.build_absolute_uri(obj.room_image2.url)
        return None

    def get_environment_image(self, obj):
        request = self.context.get("request")
        if obj.environment_image and request:
            return request.build_absolute_uri(obj.environment_image.url)
        return None

    def get_average_rating(self, obj):
        from django.db.models import Avg
        avg = obj.reviews.aggregate(Avg('rating'))['rating__avg']
        return round(float(avg), 1) if avg else 0

    def get_reviews_count(self, obj):
        return obj.reviews.count()


# [NEW] Serializer for Booking
class BookingSerializer(serializers.ModelSerializer):
    # Nested serializer to get full hotel details (Read Only)
    hotel_details = HotelListSerializer(source='hotel', read_only=True)

    class Meta:
        model = Booking
        fields = ['id', 'hotel', 'hotel_details', 'check_in', 'check_out', 'status', 'number_of_guests', 'rooms_booked', 'room', 'room_type_name', 'razorpay_order_id', 'payment_status', 'has_review', 'review_data', 'total_original_price', 'discount_amount', 'final_price', 'coupon_code', 'discount_reason', 'created_at']
        read_only_fields = ['user', 'status', 'room_type_name', 'razorpay_order_id', 'payment_status', 'has_review', 'review_data', 'total_original_price', 'discount_amount', 'final_price', 'discount_reason', 'created_at']

    coupon_code = serializers.CharField(write_only=True, required=False, allow_blank=True)

    has_review = serializers.SerializerMethodField()
    review_data = serializers.SerializerMethodField()

    def get_has_review(self, obj):
        return hasattr(obj, 'review')

    def get_review_data(self, obj):
        if hasattr(obj, 'review'):
            return {
                'id': obj.review.id,
                'rating': obj.review.rating,
                'comment': obj.review.comment,
                'created_at': obj.review.created_at,
            }
        return None

    def validate(self, data):
        """
        Check if room is available for the given dates.
        """
        hotel = data['hotel']
        check_in = data['check_in']
        check_out = data['check_out']
        number_of_guests = data.get('number_of_guests', 2)

        if check_in >= check_out:
            raise serializers.ValidationError("Check-out date must be after check-in.")

        from django.utils import timezone
        if check_in < timezone.localtime().date():
            raise serializers.ValidationError("Check-in date cannot be in the past.")

        # 1. Calculate rooms needed for THIS booking (1 room per 2 guests)
        # Use provided 'rooms_booked' or calculate minimum from guests (1 room per 2 guests)
        requested_rooms = data.get('rooms_booked')
        import math
        min_rooms = math.ceil(number_of_guests / 2)

        if not requested_rooms or requested_rooms < min_rooms:
            requested_rooms = min_rooms
            data['rooms_booked'] = requested_rooms # Ensure it's saved correctly

        # 2. Room check
        room = data.get('room')
        
        from django.utils import timezone
        from datetime import timedelta

        # A booking blocks a room only if it is 'confirmed' or already 'paid'
        blocking_filter = Q(status='confirmed') | (Q(status='pending') & Q(payment_status='paid'))
        filters = Q(hotel=hotel) & blocking_filter & Q(check_in__lt=check_out) & Q(check_out__gt=check_in)

        if room:
            filters &= Q(room=room)
            overlapping_rooms = Booking.objects.filter(filters).aggregate(total=Sum('rooms_booked'))['total'] or 0
            available_now = room.total_rooms - overlapping_rooms
            if requested_rooms > available_now:
                raise serializers.ValidationError(
                    f"Only {max(0, available_now)} rooms are available for these dates. You requested {requested_rooms}."
                )
        else:
            # Check if any single room type can satisfy the requested rooms
            rooms = Room.objects.filter(hotel=hotel)
            room_available = False
            for r in rooms:
                overlapping = Booking.objects.filter(filters & Q(room=r)).aggregate(total=Sum('rooms_booked'))['total'] or 0
                if (r.total_rooms - overlapping) >= requested_rooms:
                    room_available = True
                    break
            
            if not room_available:
                raise serializers.ValidationError(
                    f"No single room type has {requested_rooms} rooms available for these dates."
                )

        # [NEW] Discount and Pricing Logic
        user = self.context['request'].user
        room = data.get('room')
        hotel = data['hotel']
        rooms_booked = data.get('rooms_booked', 1)
        
        # Calculate base price (per night)
        price_per_night_per_room = room.price if room else hotel.price
        num_nights = (check_out - check_in).days
        total_original_price = price_per_night_per_room * rooms_booked * num_nights
        
        data['total_original_price'] = total_original_price
        
        # Identify applicable discounts
        discounts = [] # List of (percentage, reason, coupon_obj)


            
        # 3. Custom Coupon code
        coupon_code = data.pop('coupon_code', None)
        if coupon_code:

            try:
                coupon = Coupon.objects.get(
                    code__iexact=coupon_code, 
                    is_active=True
                )
                from django.utils import timezone
                # Check if booking date is within coupon validity
                if coupon.valid_from and coupon.valid_from.date() > check_in:
                     raise serializers.ValidationError({"coupon_code": "This coupon is not yet active for your booking dates."})
                if coupon.valid_to and coupon.valid_to.date() < check_in:
                     raise serializers.ValidationError({"coupon_code": "This coupon has expired for your booking dates."})
                # Check if coupon is global or for this specific hotel
                if coupon.hotel and coupon.hotel != hotel:
                    raise serializers.ValidationError({"coupon_code": "This coupon is not valid for this hotel."})
                
                discounts.append((coupon.discount_percent, f"Coupon: {coupon.code}", coupon))
            except Coupon.DoesNotExist:
                raise serializers.ValidationError({"coupon_code": "Invalid or inactive coupon code."})

        # Apply the SINGLE highest discount
        if discounts:
            best_discount = max(discounts, key=lambda x: x[0])
            discount_percent, reason, coupon_obj = best_discount
            
            discount_amount = (total_original_price * discount_percent) / 100
            data['discount_amount'] = discount_amount
            data['final_price'] = total_original_price - discount_amount
            data['discount_reason'] = reason # Track reason
            if coupon_obj:
                data['applied_coupon'] = coupon_obj
        else:
            data['discount_amount'] = 0
            data['final_price'] = total_original_price
            data['discount_reason'] = None

        return data

class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = '__all__'

class HotelGallerySerializer(serializers.ModelSerializer):
    class Meta:
        model = HotelGallery
        fields = '__all__'

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
            'id', 'booking', 'hotel', 'user', 'user_name',
            'user_email', 'rating', 'comment', 'created_at', 'images'
        ]
        read_only_fields = ['id', 'created_at', 'user', 'user_name', 'user_email', 'hotel']

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value

    def validate(self, data):
        booking = data.get('booking')
        # Only allow review if booking is completed
        if booking and booking.status not in ['confirmed', 'paid', 'completed']:
            raise serializers.ValidationError("You can only review a confirmed or completed booking.")
        # One review per booking
        if not self.instance and booking and Review.objects.filter(booking=booking).exists():
            raise serializers.ValidationError("You have already reviewed this booking.")
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        booking = validated_data['booking']
        images_data = request.FILES.getlist('images')
        
        validated_data['user'] = request.user
        validated_data['hotel'] = booking.hotel
        review = super().create(validated_data)
        
        for image_data in images_data:
            ReviewImage.objects.create(review=review, image=image_data)
        return review

class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = ['id', 'code', 'discount_percent', 'valid_from', 'valid_to', 'is_active', 'hotel']

    def validate_valid_from(self, value):
        from django.utils import timezone
        # If it's a NEW coupon (not updating), block past dates
        if not self.instance and value and value.date() < timezone.now().date():
            raise serializers.ValidationError("Coupon start date cannot be in the past.")
        return value

    def validate(self, data):
        valid_from = data.get('valid_from')
        valid_to = data.get('valid_to')
        if valid_from and valid_to and valid_from > valid_to:
            raise serializers.ValidationError("End date must be after start date.")
        return data
