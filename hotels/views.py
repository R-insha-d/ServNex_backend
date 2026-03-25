from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated, AllowAny
from rest_framework.viewsets import ModelViewSet
from rest_framework.generics import ListAPIView
from rest_framework.decorators import action
from rest_framework import status

from .models import HotelDataModel, Booking, Room, HotelGallery, NearbyAttraction, Review, Coupon # Import Coupon
from django.db.models import Q, Sum
from .serializers import (
    HotelCreateSerializer, 
    HotelListSerializer, 
    BookingSerializer,
    RoomSerializer,
    HotelGallerySerializer,
    NearbyAttractionSerializer,
    ReviewSerializer,
    CouponSerializer,
)

class HotelListAPIView(ListAPIView):
    permission_classes = [IsAuthenticatedOrReadOnly]
    queryset = HotelDataModel.objects.all()
    serializer_class = HotelListSerializer # Use ListSerializer for GET requests usually

    def get(self, request):
        hotels = HotelDataModel.objects.all()
        serializer = HotelListSerializer(hotels, many=True, context={'request': request})
        return Response(serializer.data)

class HotelViewSet(ModelViewSet):
    queryset = HotelDataModel.objects.all().order_by('-id')
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in ["POST", "PUT", "PATCH"]:
            return HotelCreateSerializer
        return HotelListSerializer

    def get_serializer_context(self):
        return {"request": self.request}

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        # Return the first hotel owned by the user
        hotel = HotelDataModel.objects.filter(owner=request.user).first()
        if not hotel:
            return Response({"error": "No hotel found for this user"}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(hotel)
        return Response(serializer.data)


# [NEW] ViewSet for Bookings
class BookingViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated] # Only logged in users can book
    serializer_class = BookingSerializer

    def get_queryset(self):
        # Users see their own bookings OR bookings for hotels they own
        # Admins (superusers) can see all
        user = self.request.user
        if user.is_superuser:
            return Booking.objects.all()
        
        # Use Q for OR logic
        return Booking.objects.filter(
            Q(user=user) | Q(hotel__owner=user)
        ).distinct().order_by('-id')

    def perform_create(self, serializer):
        # The serializer.validate() we wrote earlier handles the availability check!
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def price_preview(self, request):
        """
        Calculates price/discount without creating a booking record.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response({
            'total_original_price': data['total_original_price'],
            'discount_amount': data['discount_amount'],
            'final_price': data['final_price'],
            'discount_reason': data.get('discount_reason')
        })

    @action(detail=False, methods=['get'])
    def eligible_for_review(self, request):
        hotel_id = request.query_params.get('hotel_id')
        if not hotel_id:
            return Response({"error": "hotel_id is required"}, status=400)
        
        # Find latest completed/confirmed booking for this user/hotel that has no review
        booking = Booking.objects.filter(
            user=request.user,
            hotel_id=hotel_id,
            status__in=['confirmed', 'paid', 'completed']
        ).exclude(review__isnull=False).order_by('-created_at').first()

        if booking:
            return Response({
                "id": booking.id,
                "room_type": booking.room_type_name
            })
        return Response({"id": None})

    # Optional: Custom action to check availability without booking
    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def check_availability(self, request):
        hotel_id = request.query_params.get('hotel_id')
        room_id = request.query_params.get('room_id') # [NEW]
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        rooms_needed = int(request.query_params.get('rooms_booked', 1))

        if not all([hotel_id, check_in, check_out]):
             return Response({"error": "Missing parameters"}, status=status.HTTP_400_BAD_REQUEST)
        
        if check_in >= check_out:
            return Response({"error": "Check-out date must be after check-in date."}, status=status.HTTP_400_BAD_REQUEST)
        
        from django.utils import timezone
        if check_in < str(timezone.localtime().date()):
            return Response({"error": "Check-in date cannot be in the past."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
             hotel = HotelDataModel.objects.get(id=hotel_id)
        except HotelDataModel.DoesNotExist:
             return Response({"error": "Hotel not found"}, status=status.HTTP_404_NOT_FOUND)

        # [NEW] Room Logic
        if room_id:
             try:
                 room = Room.objects.get(id=room_id, hotel=hotel)
                 total_capacity = room.total_rooms
             except Room.DoesNotExist:
                 return Response({"error": "Room not found"}, status=status.HTTP_404_NOT_FOUND)
        else:
             # Calculate sum of all rooms for the hotel
             total_capacity = Room.objects.filter(hotel=hotel).aggregate(total=Sum('total_rooms'))['total'] or 0

        # Check existing bookings (only confirmed or recent/active pending ones block slots)
        from django.utils import timezone
        from datetime import timedelta
        pending_timeout = timezone.now() - timedelta(minutes=5)

        # A booking blocks a room if:
        # 1. It is 'confirmed'
        # 2. It is 'pending' but NOT yet 'failed' AND was created recently (last 30 mins)
        # A booking blocks a room only if it is 'confirmed' or already 'paid'
        blocking_filter = Q(status='confirmed') | (Q(status='pending') & Q(payment_status='paid'))

        filters = Q(hotel=hotel) & blocking_filter & Q(check_in__lt=check_out) & Q(check_out__gt=check_in)
        
        if room_id:
            filters &= Q(room_id=room_id)

        overlapping_rooms = Booking.objects.filter(filters).aggregate(total=Sum('rooms_booked'))['total'] or 0

        if (overlapping_rooms + rooms_needed) <= total_capacity:
             remaining = total_capacity - overlapping_rooms
             return Response({
                 "available": True,
                 "remaining_rooms": remaining
             })
        else:
             return Response({
                 "available": False,
                 "remaining_rooms": max(0, total_capacity - overlapping_rooms)
             })

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def complete_booking(self, request, pk=None):
        booking = self.get_object()
        if booking.hotel.owner != request.user:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        
        booking.status = 'completed'
        booking.save()
        return Response({"status": "Booking marked as completed"})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def cancel_booking(self, request, pk=None):
        booking = self.get_object()
        if booking.user != request.user and booking.hotel.owner != request.user:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        
        if booking.status in ['cancelled', 'completed']:
            return Response({"error": f"Booking is already {booking.status}"}, status=status.HTTP_400_BAD_REQUEST)
            
        booking.status = 'cancelled'
        booking.save()

        # Send Email to User
        from django.core.mail import send_mail
        from django.conf import settings
        try:
            send_mail(
                subject=f"Booking Cancellation Initiated - {booking.hotel.name}",
                message=f"Hello {booking.user.first_name},\n\nYour cancelation request initiated , payment will refund within 24 h.\n\nBooking ID: SNX-HTL-{booking.id}\nHotel: {booking.hotel.name}\n\nThank you.",
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[booking.user.email],
                fail_silently=True
            )
        except Exception as e:
            print(f"Failed to send email: {e}")

        return Response({"status": "Booking cancelled successfully"})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def fail_payment(self, request, pk=None):
        booking = self.get_object()
        if booking.user != request.user:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        
        booking.payment_status = 'failed'
        booking.save()
        return Response({"status": "Payment status updated to failed"})

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def eligible_for_review(self, request):
        hotel_id = request.query_params.get('hotel_id')
        if not hotel_id:
            return Response({"error": "Missing hotel_id"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check for confirmed/completed booking for this user and hotel
        booking = Booking.objects.filter(
            user=request.user, 
            hotel_id=hotel_id, 
            status__in=['confirmed', 'completed']
        ).first()
        
        if booking:
            # Also check if they ALREADY left a review
            if hasattr(booking, 'review'):
                return Response({"message": "Already reviewed"}, status=status.HTTP_200_OK)
            return Response({"id": booking.id})
        return Response({"message": "No eligible booking found"}, status=status.HTTP_200_OK)
    

class HotelDashboardView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        user = request.user
        
        # 1. Find all hotels owned by this user (e.g. "Taj Hotel" owned by User X)
        my_hotels = HotelDataModel.objects.filter(owner=user)
        
        # 2. Find all bookings for THESE hotels
        # e.g. User Y booked "Taj Hotel" -> Show this
        # e.g. User Z booked "Oberoi" (User A owner) -> Hide this
        from django.utils import timezone
        from datetime import timedelta
        pending_timeout = timezone.now() - timedelta(minutes=5)

        my_bookings = Booking.objects.filter(
            hotel__in=my_hotels, 
            status__in=['confirmed', 'completed', 'cancelled', 'pending']
        ).filter(
            Q(status__in=['confirmed', 'completed', 'cancelled']) |
            Q(status='pending', payment_status='paid') |
            Q(status='pending', created_at__gte=pending_timeout)
        ).select_related('user', 'hotel')

        
        data = []
        for booking in my_bookings:
            data.append({
                "booking_id": booking.id,
                "customer_name": booking.user.first_name or booking.user.username,
                "customer_email": booking.user.email,
                "customer_phone": booking.user.phone,
                "hotel_name": booking.hotel.name,
                "check_in": booking.check_in,
                "check_out": booking.check_out,
                "status": booking.status,
                "room_type": booking.room_type_name, # [NEW]
                "booked_at": booking.created_at,
                "rooms_booked": booking.rooms_booked,
            })
            
        return Response(data)

class RoomViewSet(ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = RoomSerializer

    def get_queryset(self):
        queryset = Room.objects.all()
        hotel_id = self.request.query_params.get('hotel')
        if hotel_id:
             queryset = queryset.filter(hotel_id=hotel_id)
        return queryset

class HotelGalleryViewSet(ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = HotelGallerySerializer

    def get_queryset(self):
        queryset = HotelGallery.objects.all()
        hotel_id = self.request.query_params.get('hotel')
        if hotel_id:
             queryset = queryset.filter(hotel_id=hotel_id)
        return queryset


class NearbyAttractionViewSet(ModelViewSet):
    permission_classes = [IsAuthenticatedOrReadOnly]
    serializer_class = NearbyAttractionSerializer

    def get_queryset(self):
        queryset = NearbyAttraction.objects.all()
        hotel_id = self.request.query_params.get("hotel")
        if hotel_id:
            queryset = queryset.filter(hotel_id=hotel_id)
        return queryset

class ReviewViewSet(ModelViewSet):
    """
    ViewSet for handling hotel reviews.
    POST: Create a review (requires completed booking)
    GET: List reviews (can filter by hotel)
    PATCH/PUT: Update owned review
    DELETE: Delete owned review
    """
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_queryset(self):
        queryset = Review.objects.all().order_by('-created_at')
        hotel_id = self.request.query_params.get('hotel')
        if hotel_id:
            queryset = queryset.filter(hotel_id=hotel_id)
        return queryset

    def get_serializer_context(self):
        return {'request': self.request}

    @action(detail=False, methods=['get'])
    def all_owner_reviews(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Get all reviews for hotels owned by the current user
        reviews = Review.objects.filter(hotel__owner=user).order_by('-created_at')
        serializer = self.get_serializer(reviews, many=True)
        return Response(serializer.data)


class CouponViewSet(ModelViewSet):
    """
    ViewSet for handling hotel coupons.
    Admin/Hotel Owner can manage coupons.
    """
    queryset = Coupon.objects.all()
    serializer_class = CouponSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        hotel_id = self.request.query_params.get('hotel')
        
        # If a hotel ID is provided, show all active coupons for that hotel
        if hotel_id:
            queryset = Coupon.objects.filter(
                hotel_id=hotel_id, 
                is_active=True
            )
            
            # [NEW] Filter by check-in date if provided
            check_in = self.request.query_params.get('check_in')
            if check_in:
                from django.utils.dateparse import parse_date
                d = parse_date(check_in)
                if d:
                    # Coupon must be valid on the check-in date
                    queryset = queryset.filter(
                        Q(valid_from__date__lte=d) | Q(valid_from__isnull=True),
                        Q(valid_to__date__gte=d) | Q(valid_to__isnull=True)
                    )
            return queryset


        if user.is_authenticated:
            if user.is_superuser:
                return Coupon.objects.all()
            # Hotel owners can manage coupons for their hotels
            return Coupon.objects.filter(hotel__owner=user)
        
        return Coupon.objects.none()

    def get_permissions(self):
        if self.action == 'list':
            return [AllowAny()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        serializer.save()
