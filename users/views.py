from django.shortcuts import render, redirect
from rest_framework import viewsets, permissions, status, parsers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
import random
from google.oauth2 import id_token
from google.auth.transport import requests

from .models import PasswordResetOTP, PendingUser
from .serializers import (
    SendOTPSerializer,
    VerifyOTPSerializer,
    ResetPasswordSerializer,
    RegisterSerializer,
    LoginSerializer,
    UserRoleUpdateSerializer,
    UserUpdateSerializer,
)

User = get_user_model()

def send_otp(user_instance):
    user_instance.generate_otp()

    send_mail(
        subject='Django App Authentication - otp',
        message=f'Your Generated OTP is : {user_instance.otp}',
        from_email='anuttananugrah@gmail.com',
        recipient_list=[user_instance.email],
        fail_silently=True

    )

class RegisterViewset(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]
    
    def create(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            # Store data in PendingUser
            email = serializer.validated_data.get('email')
            otp = str(random.randint(1000, 9999))
            
            # Create or update pending user
            PendingUser.objects.update_or_create(
                email=email,
                defaults={
                    'first_name': serializer.validated_data.get('first_name'),
                    'password': request.data.get('password'),
                    'phone': serializer.validated_data.get('phone'),
                    'role': serializer.validated_data.get('role') or (request.data.get('account_type') == 'business' and 'Business') or 'User',
                    'otp': otp
                }
            )
            
            # Use send_mail directly or update send_otp function
            send_mail(
                subject='Sign Up Verification - OTP',
                message=f'Your Verification OTP is : {otp}',
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[email],
                fail_silently=True
            )
            
            return Response({"message": "OTP sent to email. Please verify.", "redirect": "otpverify"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class OtpVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        otp_received = request.data.get('otp') or request.data.get('otpnum')
        email = request.data.get('email')

        if not email or not otp_received:
            return Response({"error": "Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pending_user = PendingUser.objects.get(email=email, otp=otp_received)
            
            # Create the actual user
            user = User.objects.create_user(
                first_name=pending_user.first_name,
                email=pending_user.email,
                password=pending_user.password,
                phone=pending_user.phone,
                role=pending_user.role
            )
            user.is_active = True
            user.is_verified = True
            user.save()
            
            # Delete pending user
            pending_user.delete()
            
            # Send success email
            send_mail(
                subject='Account Verified Successfully',
                message=f'Dear {user.first_name}, your account has been successfully verified. You can now login to ServNex.',
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[user.email],
                fail_silently=True
            )
            
            refresh = RefreshToken.for_user(user)
            return Response({
                "message": "User registered successfully",
                "user": {
                    "id": user.id,
                    "first_name": user.first_name,
                    "email": user.email,
                    "role": user.role,
                },
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            }, status=status.HTTP_201_CREATED)
            
        except PendingUser.DoesNotExist:
            return Response({"error": "Invalid OTP or Email"}, status=status.HTTP_400_BAD_REQUEST)

class ResendSignupOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            pending_user = PendingUser.objects.get(email=email)
            otp = str(random.randint(1000, 9999))
            pending_user.otp = otp
            pending_user.save()

            send_mail(
                subject='Sign Up Verification - New OTP',
                message=f'Your New Verification OTP is : {otp}',
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[email],
                fail_silently=True
            )
            return Response({"message": "New OTP sent to email."}, status=status.HTTP_200_OK)
        except PendingUser.DoesNotExist:
            return Response({"error": "No pending registration found for this email."}, status=status.HTTP_404_NOT_FOUND)

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
            context={'request': request}
        )

        if serializer.is_valid():
            user = serializer.validated_data["user"]
            refresh = RefreshToken.for_user(user)

            return Response({
                "message": "Login successful",
                "user": {
                    "id": user.id,
                    "first_name": user.first_name,
                    "email": user.email,
                    "phone": user.phone,
                    "role": getattr(user, "role", None),
                    "is_staff": user.is_staff,
                    "is_superuser": user.is_superuser,
                    "profile_image": user.profile_image.url if user.profile_image else None,
                },
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class SendOTPView(APIView):
    permission_classes = [AllowAny]  # ← Add this
    
    def post(self, request):
        print(f"📨 Received request data: {request.data}")  # Debug log
        
        serializer = SendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = User.objects.get(email=email)
        otp = str(random.randint(100000, 999999))

        # Save OTP to database
        PasswordResetOTP.objects.create(user=user, otp=otp)
        print(f"💾 OTP saved to database: {otp} for {email}")  # Debug log

        # Send email
        try:
            send_mail(
                subject="Password Reset OTP",
                message=f"Your OTP is {otp}. It is valid for 10 minutes.",
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[email],  # Send to the user's email
                fail_silently=False,
            )
            print(f"✅ Email sent successfully to {email} with OTP: {otp}")  # Debug log
            return Response({"message": "OTP sent successfully"}, status=status.HTTP_200_OK)
        
        except Exception as e:
            print(f"❌ Email sending failed: {str(e)}")  # Debug log
            return Response(
                {"error": f"Failed to send email: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class VerifyOTPView(APIView):
    permission_classes = [AllowAny]  # ← Add this
    
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.get(email=serializer.validated_data["email"])
        otp = serializer.validated_data["otp"]

        try:
            otp_obj = PasswordResetOTP.objects.filter(
                user=user, otp=otp, is_verified=False
            ).latest("created_at")
        except PasswordResetOTP.DoesNotExist:
            return Response({"error": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)

        if otp_obj.is_expired():
            return Response({"error": "OTP expired"}, status=status.HTTP_400_BAD_REQUEST)

        otp_obj.is_verified = True
        otp_obj.save()

        return Response({"message": "OTP verified"}, status=status.HTTP_200_OK)

class ResetPasswordView(APIView):
    permission_classes = [AllowAny]  # ← Add this
    
    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.get(email=serializer.validated_data["email"])

        if not PasswordResetOTP.objects.filter(user=user, is_verified=True).exists():
            return Response(
                {"error": "OTP not verified"}, status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data["password"])
        user.save()

        PasswordResetOTP.objects.filter(user=user).delete()

        return Response(
            {"message": "Password reset successful"}, status=status.HTTP_200_OK
        )

class UpdateRoleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        serializer = UserRoleUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Role updated successfully", "role": serializer.data['role']}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

from hotels.models import HotelDataModel
from restaurants.models import RestaurantDataModel
from salons.models import SalonDataModel

class BusinessProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        data = request.data
        
        if user.role == 'Hotel':
            hotel = HotelDataModel.objects.create(
                owner=user,
                name=data.get('name'),
                city=data.get('city'),
                area=data.get('area'),
                description=data.get('description'),
            )
            return Response({"message": "Hotel profile created", "id": hotel.id}, status=status.HTTP_201_CREATED)
            
        elif user.role == 'Restaurant': 
            restaurant = RestaurantDataModel.objects.create(
                owner=user,
                name=data.get('name'),
                city=data.get('city'),
                area=data.get('area'),
                description=data.get('description'),
            )
            return Response({"message": "Restaurant profile created", "id": restaurant.id}, status=status.HTTP_201_CREATED)
            
        elif user.role == 'Saloon':
            salon = SalonDataModel.objects.create(
                owner=user,
                name=data.get('name'),
                city=data.get('city'),
                area=data.get('area'),
                description=data.get('description'),
            )
            return Response({"message": "Salon profile created", "id": salon.id}, status=status.HTTP_201_CREATED)
            
        else:
            return Response({"error": "Invalid role for business profile"}, status=status.HTTP_400_BAD_REQUEST)

class UserProfileUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    def patch(self, request):
        serializer = UserUpdateSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            user = serializer.save()
            
            return Response({
                "message": "Profile updated successfully",
                "user": {
                    "id": user.id,
                    "first_name": user.first_name,
                    "email": user.email,
                    "phone": user.phone,
                    "role": getattr(user, "role", None),
                    "profile_image": user.profile_image.url if user.profile_image else None,
                }
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request):
        user = request.user
        user.delete()
        return Response({"message": "User account deleted successfully"}, status=status.HTTP_204_NO_CONTENT)

class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get("credential")
        access_token = request.data.get("access_token")
        
        if not token and not access_token:
            return Response({"error": "Credential or access_token is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client_id = "517231673876-5rciu4craia4j2kd6lr9mp4htoi3toad.apps.googleusercontent.com"
            
            if token:
                # Flow for ID Token (credential)
                idinfo = id_token.verify_oauth2_token(token, requests.Request(), client_id)
                if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                    raise ValueError('Wrong issuer.')
                email = idinfo['email']
                first_name = idinfo.get('given_name', idinfo.get('name', ''))
                picture = idinfo.get('picture', None)
            else:
                # Flow for Access Token
                import requests as py_requests
                response = py_requests.get(f"https://www.googleapis.com/oauth2/v3/userinfo?access_token={access_token}")
                if response.status_code != 200:
                    raise ValueError("Invalid access token")
                user_info = response.json()
                email = user_info['email']
                first_name = user_info.get('given_name', user_info.get('name', ''))
                picture = user_info.get('picture', None)

            # Use get_or_create to find or create the user by email
            user, created = User.objects.get_or_create(email=email, defaults={
                'first_name': first_name,
                'is_verified': True,
                'is_active': True,
                'role': 'User'
            })

            if not user.is_active:
                return Response({"error": "User account is suspended"}, status=status.HTTP_403_FORBIDDEN)

            refresh = RefreshToken.for_user(user)

            return Response({
                "message": "Login successful",
                "user": {
                    "id": user.id,
                    "first_name": user.first_name,
                    "email": user.email,
                    "phone": user.phone,
                    "role": user.role,
                    "is_staff": user.is_staff,
                    "is_superuser": user.is_superuser,
                    "profile_image": user.profile_image.url if user.profile_image else picture,
                },
                "access": str(refresh.access_token),
                "refresh": str(refresh)
            }, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Google Login Exception: {str(e)}")
            return Response({"error": "Failed to verify Google account"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
