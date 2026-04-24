from rest_framework import serializers
from .models import SalonDataModel, SalonService, SalonQueueEntry, Review, ReviewImage, SalonGallery
from django.contrib.auth import get_user_model

User = get_user_model()

class SalonServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalonService
        fields = ['id', 'salon', 'name', 'description', 'price', 'duration']

class SalonCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalonDataModel
        fields = [
            'name', 'city', 'area', 'address', 'phone', 
            'description', 'badge', 'image', 'amenities', 
            'latitude', 'longitude', 'keywords', 'is_open', 
            'opening_time', 'closing_time'
        ]

    def create(self, validated_data):
        # Automatically assign the logged-in user as the owner
        user = self.context['request'].user
        return SalonDataModel.objects.create(owner=user, **validated_data)

class SalonGallerySerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = SalonGallery
        fields = ['id', 'image']

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

class ReviewImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewImage
        fields = ['id', 'image', 'created_at']

class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    images = ReviewImageSerializer(many=True, read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'salon', 'queue_entry', 'user', 'user_name', 'rating', 'comment', 'created_at', 'images']
        read_only_fields = ['id', 'user', 'created_at']

class SalonListSerializer(serializers.ModelSerializer):
    service_type = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    reviews_count = serializers.SerializerMethodField()
    amenities = serializers.SerializerMethodField()
    all_services = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = SalonDataModel
        fields = [
            'id', 'name', 'city', 'area', 'badge', 'image', 
            'rating', 'service_type', 'all_services', 'average_rating', 'reviews_count',
            'amenities', 'latitude', 'longitude'
        ]

    def get_service_type(self, obj):
        service = obj.services.first()
        return service.name if service else "Styling"

    def get_all_services(self, obj):
        return list(obj.services.values_list('name', flat=True))

    def get_average_rating(self, obj):
        from django.db.models import Avg
        avg = obj.reviews.aggregate(Avg('rating'))['rating__avg']
        return round(float(avg), 1) if avg else float(obj.rating or 0.0)

    def get_reviews_count(self, obj):
        return obj.reviews.count()

    def get_amenities(self, obj):
        if obj.amenities:
            return [a.strip() for a in obj.amenities.split(',') if a.strip()]
        return []

    def get_image(      self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

class SalonDetailSerializer(serializers.ModelSerializer):
    services = SalonServiceSerializer(many=True, read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    amenities = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    gallery = SalonGallerySerializer(many=True, read_only=True)
    
    class Meta:
        model = SalonDataModel
        fields = [
            'id', 'name', 'city', 'area', 'address', 'phone', 
            'description', 'badge', 'image', 'gallery', 'amenities', 
            'latitude', 'longitude', 'rating', 'services', 'reviews',
            'is_open', 'opening_time', 'closing_time'
        ]

    def get_amenities(self, obj):
        if obj.amenities:
            return [a.strip() for a in obj.amenities.split(',') if a.strip()]
        return []

    def get_image(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

class SalonQueueEntrySerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    salon_name = serializers.CharField(source='salon.name', read_only=True)
    salon_image = serializers.ImageField(source='salon.image', read_only=True)
    salon_area = serializers.CharField(source='salon.area', read_only=True)
    salon_city = serializers.CharField(source='salon.city', read_only=True)
    service_name = serializers.CharField(source='service.name', read_only=True)
    created_at = serializers.DateTimeField(source='joined_at', read_only=True)
    has_review = serializers.SerializerMethodField()
    review_data = serializers.SerializerMethodField()

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return obj.guest_name or "Guest Customer"

    class Meta:
        model = SalonQueueEntry
        fields = [
            'id', 'user', 'user_name', 'user_phone', 'salon', 'salon_name', 'salon_image',
            'salon_area', 'salon_city', 'service', 'service_name', 
            'status', 'joined_at', 'created_at', 'estimated_wait_time', 
            'guest_name', 'guest_phone',
            'has_review', 'review_data'
        ]
        read_only_fields = ['id', 'user', 'joined_at', 'created_at', 'has_review', 'review_data']

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
