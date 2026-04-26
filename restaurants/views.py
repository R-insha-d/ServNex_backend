from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from .models import RestaurantDataModel, TableReservation, Review
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .serializers import RestaurantSerializer, TableReservationSerializer,ReviewSerializer
from notifications.models import Notification
import razorpay
from django.conf import settings
from django.utils import timezone
from datetime import datetime, time, timedelta
from django.contrib.contenttypes.models import ContentType
from payments.models import Payment

from math import radians, cos, sin, asin, sqrt

# Initialize Razorpay Client
client = razorpay.Client(auth=(settings.RAZR_KEY_ID, settings.RAZR_KEY_SECRET))


class RestaurantListCreateView(generics.ListCreateAPIView):
    serializer_class = RestaurantSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        queryset = RestaurantDataModel.objects.all()

        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        radius = self.request.query_params.get('radius', 10)  # default 10 km

        # 🔍 If location is provided → filter by distance
        if lat and lng:
            try:
                lat = float(lat)
                lng = float(lng)
                radius = float(radius)

                nearby_restaurants = []

                for restaurant in queryset:
                    # if restaurant.latitude and restaurant.longitude:
                    if restaurant.latitude is not None and restaurant.longitude is not None:
                        distance = haversine(
                            lat, lng,
                            restaurant.latitude,
                            restaurant.longitude
                        )

                        if distance <= radius:
                            restaurant.distance = round(distance, 2)
                            nearby_restaurants.append(restaurant)

                # 🔥 Sort by nearest
                nearby_restaurants.sort(key=lambda x: x.distance)

                return nearby_restaurants

            except Exception as e:
                print("Location filter error:", e)
                return queryset

        return queryset

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

        # ----------------------------------------


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
        3
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
        
        old_status = instance.status
        updated_instance = serializer.save()
        
        # Check for status changes to notify user
        if updated_instance.status == 'Your Table Is Ready' and old_status != 'Your Table Is Ready':
            Notification.objects.create(
                user=updated_instance.user,
                title="Table Ready!",
                message=f"Your table at {updated_instance.restaurant.name} is now ready. Please head to the restaurant.",
                notification_type='reservation',
                link=f"/my-bookings"
            )
        
        if updated_instance.status == 'cancelled':
            # ── REFUND POLICY CALCULATOR ──
            now = timezone.now()
            # Combine date and time to get the reservation datetime
            reservation_dt = timezone.make_aware(datetime.combine(
                updated_instance.reservation_date, 
                updated_instance.reservation_time
            ))
            
            # Policy rules
            hours_diff = (reservation_dt - now).total_seconds() / 3600
            booking_age_mins = (now - updated_instance.created_at).total_seconds() / 60
            
            refund_percentage = 0.0
            reason = "No refund (reservation time has passed)"

            if booking_age_mins <= 10:
                refund_percentage = 1.0
                reason = "Full refund (Grace Period - cancelled within 10 mins of booking)"
            elif hours_diff >= 2:
                refund_percentage = 1.0
                reason = "Full refund (≥ 2 hours before reservation)"
            elif reservation_dt > now:
                refund_percentage = 0.5
                reason = "Partial refund (50% - cancelled within 2 hours of reservation)"
            
            refund_status = "Not applicable"
            refund_id = None

            if refund_percentage > 0:
                try:
                    content_type = ContentType.objects.get_for_model(TableReservation)
                    payment = Payment.objects.filter(
                        content_type=content_type,
                        object_id=updated_instance.id,
                        status='success'
                    ).first()

                    if payment and payment.razorpay_payment_id:
                        refund_amount = int(float(payment.amount) * refund_percentage * 100)
                        refund_resp = client.payment.refund(payment.razorpay_payment_id, {
                            "amount": refund_amount,
                            "notes": {"reason": reason, "reservation_id": updated_instance.id}
                        })
                        refund_id = refund_resp.get('id')
                        refund_status = f"Initiated ({int(refund_percentage*100)}% refund)"
                    else:
                        refund_status = "Skipped (No successful payment found)"
                except Exception as e:
                    print(f"Razorpay Refund Error: {e}")
                    refund_status = f"Failed to automate ({str(e)})"

            # Notify User of cancellation
            Notification.objects.create(
                user=updated_instance.user,
                title="Reservation Cancelled",
                message=f"Your reservation for {updated_instance.restaurant.name} has been cancelled. Refund status: {refund_status}.",
                notification_type='reservation',
                link=f"/my-bookings"
            )
            
            # Notify Owner of cancellation (if cancelled by user)
            if self.request.user == updated_instance.user and updated_instance.restaurant.owner:
                Notification.objects.create(
                    user=updated_instance.restaurant.owner,
                    title="Reservation Cancelled",
                    message=f"The reservation for {updated_instance.restaurant.name} by {updated_instance.user.first_name or updated_instance.user.username} has been cancelled.",
                    notification_type='reservation',
                    link=f"/restaurant-dashboard"
                )

            # Send Email
            from django.core.mail import send_mail
            from django.conf import settings
            
            email_message = (
                f"Hello {updated_instance.user.first_name},\n\n"
                f"Your reservation for {updated_instance.restaurant.name} has been cancelled successfully.\n\n"
                f"Refund Details:\n"
                f"- Policy: {reason}\n"
                f"- Status: {refund_status}\n"
            )
            if refund_id:
                email_message += f"- Refund ID: {refund_id}\n"
            
            email_message += (
                f"\nReservation ID: SNX-RES-{updated_instance.id}\n"
                f"Restaurant: {updated_instance.restaurant.name}\n"
                f"Date: {updated_instance.reservation_date}\n"
                f"Time: {updated_instance.reservation_time}\n\n"
                f"Thank you for choosing ServNex."
            )

            try:
                send_mail(
                    subject=f"Reservation Cancelled - {updated_instance.restaurant.name}",
                    message=email_message,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[updated_instance.user.email],
                    fail_silently=True
                )
            except Exception as e:
                print(f"Failed to send email: {e}")


class RestaurantMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

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
        ).order_by('reservation_date', 'reservation_time').select_related('user', 'restaurant')
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
    permission_classes = [permissions.AllowAny]

    def get(self, request, pk):
        date_str = request.query_params.get('date')
        if not date_str:
            return Response({"error": "date is required"}, status=400)
        
        try:
            restaurant = RestaurantDataModel.objects.get(pk=pk)
        except RestaurantDataModel.DoesNotExist:
            return Response({"error": "Restaurant not found"}, status=404)

        capacities = [2, 4, 6, 8, 10]
        availability = {}

        reservations = TableReservation.objects.filter(
            restaurant=restaurant,
            reservation_date=date_str
        ).filter(
            Q(payment_status='paid') | Q(status__in=['Your Table Is Ready', 'completed'])
        ).exclude(status='cancelled')

        for cap in capacities:
            booked = 0

            for res in reservations:
                sel = res.table_selection or {}
                booked += int(sel.get(str(cap), 0))

            total = getattr(restaurant, f'tables_{cap}_capacity', 0)
            availability[str(cap)] = max(0, total - booked)  # 👈 string key

        return Response(availability)
    

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in KM

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * asin(sqrt(a))

    return R * c


