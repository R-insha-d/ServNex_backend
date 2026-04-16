import razorpay
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.contrib.contenttypes.models import ContentType
from .models import Payment
from .serializers import RazorpayOrderSerializer, RazorpayPaymentVerificationSerializer
from hotels.models import Booking
from restaurants.models import TableReservation
from notifications.models import Notification

client = razorpay.Client(auth=(settings.RAZR_KEY_ID, settings.RAZR_KEY_SECRET))

class CreateRazorpayOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = RazorpayOrderSerializer(data=request.data)
        if serializer.is_valid():
            amount = int(serializer.validated_data['amount'] * 100)  # Amount in paise
            booking_type = serializer.validated_data['booking_type']
            booking_id = serializer.validated_data['booking_id']

            # Create Razorpay Order
            data = {
                "amount": amount,
                "currency": "INR",
                "payment_capture": "1"
            }
            try:
                razorpay_order = client.order.create(data=data)
                
                # Link to internal model
                if booking_type == 'hotel':
                    content_type = ContentType.objects.get_for_model(Booking)
                else:
                    content_type = ContentType.objects.get_for_model(TableReservation)

                # Store pending payment in centralized table
                Payment.objects.create(
                    user=request.user,
                    amount=serializer.validated_data['amount'],
                    razorpay_order_id=razorpay_order['id'],
                    content_type=content_type,
                    object_id=booking_id,
                    status='pending'
                )

                # ALSO Update the specific booking object with the order ID
                booking_obj = None
                if booking_type == 'hotel':
                    booking_obj = Booking.objects.get(id=booking_id)
                else:
                    booking_obj = TableReservation.objects.get(id=booking_id)
                
                if booking_obj:
                    booking_obj.razorpay_order_id = razorpay_order['id']
                    booking_obj.save()

                return Response(razorpay_order, status=status.HTTP_201_CREATED)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class VerifyPaymentView(APIView):

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = RazorpayPaymentVerificationSerializer(data=request.data)
        if serializer.is_valid():
            razorpay_order_id = serializer.validated_data['razorpay_order_id']
            razorpay_payment_id = serializer.validated_data['razorpay_payment_id']
            razorpay_signature = serializer.validated_data['razorpay_signature']

            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            }

            try:
                # Verify Signature
                client.utility.verify_payment_signature(params_dict)
                
                # Update Payment object
                payment = Payment.objects.get(razorpay_order_id=razorpay_order_id)
                payment.razorpay_payment_id = razorpay_payment_id
                payment.razorpay_signature = razorpay_signature
                payment.status = 'success'
                payment.save()

                # Update the actual Booking/Reservation model
                booking_obj = payment.content_object
                if booking_obj:
                    # Update the payment_status field added earlier
                    if hasattr(booking_obj, 'payment_status'):
                        booking_obj.payment_status = 'paid'
                    
                    # For Hotels, we might also want to ensure status is 'confirmed'
                    if isinstance(booking_obj, Booking):
                        booking_obj.status = 'confirmed'
                        
                    booking_obj.save()

                    # ── CREATE NOTIFICATIONS (ONLY if status is now 'success') ──
                    # This double-check ensures we never send confirmed notifications twice or on failed attempts
                    if payment.status == 'success':
                        if isinstance(booking_obj, Booking):
                            # Notify User
                            Notification.objects.create(
                                user=booking_obj.user,
                                title="Booking Confirmed",
                                message=f"Your booking for {booking_obj.hotel.name} has been confirmed. Get ready for your stay!",
                                notification_type='booking',
                                link=f"/my-bookings"
                            )
                            # Notify Hotel Owner
                            if booking_obj.hotel.owner:
                                Notification.objects.create(
                                    user=booking_obj.hotel.owner,
                                    title="New Confirmed Booking",
                                    message=f"You have a new confirmed booking for {booking_obj.hotel.name} from {booking_obj.user.first_name or booking_obj.user.username}.",
                                    notification_type='booking',
                                    link=f"/admin-dashboard"
                                )
                        else:
                            # TableReservation - Notify User
                            Notification.objects.create(
                                user=booking_obj.user,
                                title="Reservation Confirmed",
                                message=f"Your table reservation for {booking_obj.restaurant.name} on {booking_obj.reservation_date} has been confirmed.",
                                notification_type='reservation',
                                link=f"/my-bookings"
                            )
                            # TableReservation - Notify Restaurant Owner
                            if booking_obj.restaurant.owner:
                                Notification.objects.create(
                                    user=booking_obj.restaurant.owner,
                                    title="New Confirmed Reservation",
                                    message=f"New confirmed reservation for {booking_obj.restaurant.name} from {booking_obj.user.first_name or booking_obj.user.username}.",
                                    notification_type='reservation',
                                    link=f"/restaurant-dashboard"
                                )

                        # Send Email to Business Owner
                        owner_email = None
                        if isinstance(booking_obj, Booking) and getattr(booking_obj.hotel.owner, 'email', None):
                            owner_email = booking_obj.hotel.owner.email
                            subject = f"New Booking Confirmed - {booking_obj.hotel.name}"
                            message = f"Hello,\n\nA new booking has been confirmed for {booking_obj.hotel.name} by {booking_obj.user.first_name}.\n\nDetails:\nCheck-in: {booking_obj.check_in}\nCheck-out: {booking_obj.check_out}\nRooms Booked: {booking_obj.rooms_booked}\n\nThis booking is fully paid and confirmed.\n\nThank you!"
                        elif hasattr(booking_obj, 'restaurant') and getattr(booking_obj.restaurant.owner, 'email', None):
                            owner_email = booking_obj.restaurant.owner.email
                            subject = f"New Table Reservation - {booking_obj.restaurant.name}"
                            message = f"Hello,\n\nA new table reservation has been confirmed for {booking_obj.restaurant.name} by {booking_obj.user.first_name}.\n\nDetails:\nDate: {booking_obj.reservation_date}\nTime: {booking_obj.reservation_time}\nGuests: {booking_obj.number_of_guests}\n\nThis reservation is fully paid and confirmed.\n\nThank you!"

                        if owner_email:
                            from django.core.mail import send_mail
                            try:
                                send_mail(
                                    subject=subject,
                                    message=message,
                                    from_email=settings.EMAIL_HOST_USER,
                                    recipient_list=[owner_email],
                                    fail_silently=True
                                )
                            except Exception as e:
                                print(f"Failed to send email: {e}")

                return Response({"status": "Payment Verified Successfully"}, status=status.HTTP_200_OK)
            except razorpay.errors.SignatureVerificationError:
                payment = Payment.objects.filter(razorpay_order_id=razorpay_order_id).first()
                if payment:
                    payment.status = 'failed'
                    payment.save()
                    
                    # Notify User of Failure
                    Notification.objects.create(
                        user=payment.user,
                        title="Payment Failed",
                        message=f"Your payment for order {razorpay_order_id} was not successful. Please try again.",
                        notification_type='failure',
                        link="/my-bookings"
                    )
                return Response({"error": "Invalid Signature"}, status=status.HTTP_400_BAD_REQUEST)
            except Payment.DoesNotExist:
                return Response({"error": "Payment record not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class HandlePaymentFailureView(APIView):
    """
    Explicitly handle payment failures reported by the frontend 
    (e.g. when a user cancels the Razorpay popup).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        razorpay_order_id = request.data.get('razorpay_order_id')
        error_description = request.data.get('error_description', "Payment was not completed.")

        if not razorpay_order_id:
            return Response({"error": "Missing razorpay_order_id"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            payment = Payment.objects.get(razorpay_order_id=razorpay_order_id)
            
            # Update Payment status
            if payment.status == 'pending':
                payment.status = 'failed'
                payment.save()

                # Update associated booking/reservation
                booking_obj = payment.content_object
                if booking_obj and getattr(booking_obj, 'payment_status', None) != 'paid':
                    booking_obj.payment_status = 'failed'
                    booking_obj.save()

                # Create Notification
                Notification.objects.create(
                    user=payment.user,
                    title="Payment Failed",
                    message=f"The payment for your {payment.content_type.model.replace('_', ' ')} could not be processed. {error_description}",
                    notification_type='failure',
                    link="/my-bookings"
                )
                return Response({"status": "Failure recorded and notification sent"}, status=status.HTTP_200_OK)
            else:
                return Response({"status": f"Payment already in state: {payment.status}"}, status=status.HTTP_200_OK)

        except Payment.DoesNotExist:
            return Response({"error": "Payment record not found"}, status=status.HTTP_404_NOT_FOUND)
