from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from .models import RestaurantDataModel, TableReservation, Review
from rest_framework.parsers import MultiPartParser, FormParser
from .serializers import RestaurantSerializer, TableReservationSerializer,ReviewSerializer


class RestaurantListCreateView(generics.ListCreateAPIView):
    """
    GET: List all restaurants
    POST: Create a new restaurant (business owners only)
    """
    queryset = RestaurantDataModel.objects.all()
    serializer_class = RestaurantSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]  # Authenticated users can create, anyone can view

    def perform_create(self, serializer):
        # Automatically set the owner to the logged-in user
        serializer.save(owner=self.request.user)


class RestaurantDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Retrieve a specific restaurant
    PUT/PATCH: Update restaurant details (owner only)
    DELETE: Delete restaurant (owner only)
    """
    queryset = RestaurantDataModel.objects.all()
    serializer_class = RestaurantSerializer
    permission_classes = [permissions.AllowAny]  # Anyone can view

    def get_permissions(self):
        # Only owner can update/delete
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]


class TableReservationListCreateView(generics.ListCreateAPIView):
    """
    GET: List all reservations (admin only)
    POST: Create a new reservation (authenticated users)
    """
    queryset = TableReservation.objects.all()
    serializer_class = TableReservationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        # Automatically set the user to the logged-in user
        serializer.save(user=self.request.user)


class UserReservationsView(generics.ListAPIView):
    """
    GET: List all reservations for the logged-in user
    """
    serializer_class = TableReservationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TableReservation.objects.filter(user=self.request.user)

class EligibleReservationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        restaurant_id = request.query_params.get('restaurant_id')
        if not restaurant_id:
            return Response({"error": "restaurant_id is required"}, status=400)
        
        reservation = TableReservation.objects.filter(
            user=request.user,
            restaurant_id=restaurant_id,
            status__in=['Your Table Is Ready', 'completed', 'paid']
        ).exclude(review__isnull=False).order_by('-created_at').first()

        if reservation:
            return Response({"id": reservation.id})
        return Response({"id": None})


class RestaurantReservationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TableReservationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return TableReservation.objects.filter(
            Q(user=user) | Q(restaurant__owner=user)
        )

    def perform_update(self, serializer):
        from rest_framework.exceptions import ValidationError
        instance = self.get_object()
        if instance.status in ['cancelled', 'completed']:
            raise ValidationError(detail=f"Reservation is already {instance.status}")
        
        updated_instance = serializer.save()
        
        if updated_instance.status == 'cancelled':
            from django.core.mail import send_mail
            from django.conf import settings
            try:
                send_mail(
                    subject=f"Reservation Cancellation Initiated - {updated_instance.restaurant.name}",
                    message=f"Hello {updated_instance.user.first_name},\n\nYour cancelation request initiated , payment will refund within 24 h.\n\nReservation ID: SNX-RES-{updated_instance.id}\nRestaurant: {updated_instance.restaurant.name}\n\nThank you.",
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[updated_instance.user.email],
                    fail_silently=True
                )
            except Exception as e:
                print(f"Failed to send email: {e}")


class RestaurantMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        try:
            restaurant = RestaurantDataModel.objects.get(owner=request.user)
            serializer = RestaurantSerializer(restaurant, context={'request': request})
            return Response(serializer.data)
        except RestaurantDataModel.DoesNotExist:
            return Response({"error": "No restaurant found"}, status=404)

    def patch(self, request):
        try:
            restaurant = RestaurantDataModel.objects.get(owner=request.user)
        except RestaurantDataModel.DoesNotExist:
            return Response({"error": "No restaurant found"}, status=404)

        serializer = RestaurantSerializer(
            restaurant, data=request.data, partial=True, context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


class RestaurantDashboardReservationsView(APIView):
    """Active reservations only — completed ones go to Previous Records tab"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        reservations = TableReservation.objects.filter(
            restaurant__owner=request.user,
            payment_status='paid'
        ).exclude(
            status__in=['completed', 'cancelled']
        ).select_related('user', 'restaurant')
        serializer = TableReservationSerializer(reservations, many=True)
        return Response(serializer.data)


class RestaurantPreviousRecordsView(APIView):
    """Completed reservations with reviews for the Previous Records tab"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        reservations = TableReservation.objects.filter(
            restaurant__owner=request.user,
            status='completed'
        ).select_related('user', 'restaurant').prefetch_related('review')
        serializer = TableReservationSerializer(reservations, many=True)
        return Response(serializer.data)


class ReviewCreateView(generics.CreateAPIView):
    """User submits a star rating + comment for their completed reservation"""
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        return {'request': self.request}


class RestaurantReviewsView(generics.ListAPIView):
    """All reviews for a restaurant — used in dashboard previous records"""
    serializer_class = ReviewSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Review.objects.filter(restaurant_id=self.kwargs.get('pk'))


class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET, PUT, PATCH, DELETE for a specific review"""
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only edit/delete their own reviews
        return Review.objects.filter(user=self.request.user)


class RestaurantAvailabilityView(APIView):
    """
    GET: Check availability for all table types (4, 6, 8, 10) for a given date
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({"error": "date is required"}, status=400)
        
        try:
            restaurant = RestaurantDataModel.objects.get(pk=pk)
        except RestaurantDataModel.DoesNotExist:
            return Response({"error": "Restaurant not found"}, status=404)

        capacities = [4, 6, 8, 10]
        availability = {}
        
        for cap in capacities:
            booked = TableReservation.objects.filter(
                restaurant=restaurant,
                reservation_date=date_str,
                table_capacity=cap
            ).filter(
                Q(payment_status='paid') | Q(status__in=['Your Table Is Ready', 'completed'])
            ).count()
            
            total = getattr(restaurant, f'tables_{cap}_capacity', 0)
            availability[cap] = max(0, total - booked)
            
        return Response(availability)
