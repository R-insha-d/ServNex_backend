from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
from .models import SalonDataModel, SalonService, SalonQueueEntry, Review, SalonGallery
from .serializers import (
    SalonListSerializer, SalonDetailSerializer, SalonCreateSerializer,
    SalonServiceSerializer, SalonQueueEntrySerializer, ReviewSerializer,
    SalonGallerySerializer
)
from notifications.models import Notification
from .permissions import IsSalonOwnerOrReadOnly

class SalonViewSet(viewsets.ModelViewSet):
    queryset = SalonDataModel.objects.all().order_by('-id')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SalonListSerializer
        if self.action == 'retrieve':
            return SalonDetailSerializer
        if self.action in ['create', 'update', 'partial_update']:
            return SalonCreateSerializer
        return SalonListSerializer

    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated(), IsSalonOwnerOrReadOnly()]
        if self.action == 'create':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def me(self, request):
        """Returns the salon profile owned by the current user"""
        salon = SalonDataModel.objects.filter(owner=request.user).first()
        if not salon:
            return Response({"error": "No salon found for this user"}, status=status.HTTP_404_NOT_FOUND)
        serializer = SalonDetailSerializer(salon, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['patch'], permission_classes=[permissions.IsAuthenticated])
    def update_me(self, request):
        """Allows owner to update their salon profile"""
        salon = SalonDataModel.objects.filter(owner=request.user).first()
        if not salon:
            return Response({"error": "No salon found"}, status=status.HTTP_404_NOT_FOUND)
            
        # Ensure data is mutable for processing
        data = request.data.copy() if hasattr(request.data, 'copy') else request.data
        
        serializer = SalonCreateSerializer(salon, data=data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        # Return the full detail view after update
        return Response(SalonDetailSerializer(salon, context={'request': request}).data)

    @action(detail=True, methods=['get'], permission_classes=[permissions.AllowAny], url_path='queue-status')
    def queue_status(self, request, pk=None):
        """Returns current queue length and estimated wait time for a salon"""
        salon = self.get_object()
        pending_entries = SalonQueueEntry.objects.filter(salon=salon, status='pending')
        in_service_entries = SalonQueueEntry.objects.filter(salon=salon, status='in_progress')
        
        estimated_wait = 0
        
        # Calculate wait time from pending people
        for entry in pending_entries:
            try:
                # Extract numbers from duration string (e.g., "30 mins" -> 30)
                duration = int(''.join(filter(str.isdigit, entry.service.duration or "20")))
                estimated_wait += duration
            except ValueError:
                estimated_wait += 20 # Default fallback
                
        # Calculate wait time from people currently in service (assume half time left)
        for entry in in_service_entries:
            try:
                duration = int(''.join(filter(str.isdigit, entry.service.duration or "20")))
                estimated_wait += (duration // 2) 
            except ValueError:
                estimated_wait += 10 # Default fallback
        
        return Response({
            "current_queue_length": pending_entries.count(),
            "estimated_wait_time": estimated_wait
        })

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='join-queue')
    def join_queue(self, request, pk=None):
        """Allows a user to join the virtual queue for a specific service"""
        salon = self.get_object()
        service_id = request.data.get('service_id')
        service_name = request.data.get('service') # Frontend might send service name

        if service_id:
            try:
                service = SalonService.objects.get(id=service_id, salon=salon)
            except (SalonService.DoesNotExist, ValueError):
                return Response({"error": "Invalid service ID"}, status=status.HTTP_400_BAD_REQUEST)
        elif service_name:
            service = SalonService.objects.filter(salon=salon, name=service_name).first()
            if not service:
                return Response({"error": f"Service '{service_name}' not found"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"error": "Please select a service"}, status=status.HTTP_400_BAD_REQUEST)

        # ── Operating Hours & Workload Check ──
        # Skip check if the requester is the salon owner (manual entry)
        is_owner = salon.owner == request.user
        if not is_owner:
            now = timezone.now()
            
            # Check if salon is currently open
            current_time = now.time()
            if salon.opening_time and salon.closing_time:
                if current_time < salon.opening_time or current_time > salon.closing_time:
                    return Response({"error": "Salon is currently closed."}, status=status.HTTP_400_BAD_REQUEST)

            # Calculate total workload (current queue + new service + buffer)
            active_entries = SalonQueueEntry.objects.filter(salon=salon, status__in=['pending', 'in_progress'])
            total_workload_mins = 0
            
            for entry in active_entries:
                try:
                    # Extract numeric duration
                    d = int(''.join(filter(str.isdigit, entry.service.duration or "30")))
                    total_workload_mins += d
                except:
                    total_workload_mins += 30
            
            # Add requested service duration
            try:
                new_service_duration = int(''.join(filter(str.isdigit, service.duration or "30")))
                total_workload_mins += new_service_duration
            except:
                total_workload_mins += 30
                
            # Add buffer time (e.g., 15 mins)
            buffer_mins = 15
            total_workload_mins += buffer_mins
            
            # Calculate projected finish time
            projected_finish_dt = now + timedelta(minutes=total_workload_mins)
            closing_dt = timezone.make_aware(datetime.combine(now.date(), salon.closing_time))
            
            if projected_finish_dt > closing_dt:
                return Response({
                    "error": f"Cannot accommodate this service today. Estimated completion time ({projected_finish_dt.strftime('%H:%M')}) exceeds salon closing time ({salon.closing_time.strftime('%H:%M')}).",
                    "details": {
                        "estimated_completion": projected_finish_dt.strftime('%H:%M'),
                        "closing_time": salon.closing_time.strftime('%H:%M')
                    }
                }, status=status.HTTP_400_BAD_REQUEST)

        # Check for existing active queue entry (Only for regular users)
        if not is_owner:
            if SalonQueueEntry.objects.filter(user=request.user, salon=salon, status__in=['pending', 'in_progress']).exists():
                return Response({"error": "You are already in the queue for this salon"}, status=status.HTTP_400_BAD_REQUEST)

        # Create entry
        guest_name = request.data.get('guest_name')
        guest_phone = request.data.get('guest_phone')

        entry = SalonQueueEntry.objects.create(
            user=None if is_owner and guest_name else request.user,
            guest_name=guest_name if is_owner else None,
            guest_phone=guest_phone if is_owner else None,
            salon=salon,
            service=service,
            status='pending'
        )

        # Notify user about joining the queue (Only for registered users)
        if entry.user:
            Notification.objects.create(
                user=entry.user,
                title="Joined Queue",
                message=f"You've successfully joined the queue at {salon.name} for {service.name}.",
                notification_type='booking',
                link='/my-bookings'
            )
        return Response(SalonQueueEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

class SalonServiceViewSet(viewsets.ModelViewSet):
    queryset = SalonService.objects.all()
    serializer_class = SalonServiceSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsSalonOwnerOrReadOnly]

    def get_queryset(self):
        salon_id = self.request.query_params.get('salon')
        if salon_id:
            return SalonService.objects.filter(salon_id=salon_id)
        return super().get_queryset()

class SalonQueueEntryViewSet(viewsets.ModelViewSet):
    queryset = SalonQueueEntry.objects.all()
    serializer_class = SalonQueueEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return SalonQueueEntry.objects.all()
        # Users see their own, owners see their salon's
        return SalonQueueEntry.objects.filter(Q(user=user) | Q(salon__owner=user)).distinct().order_by('-joined_at')

    def partial_update(self, request, *args, **kwargs):
        """Allows status updates by the owner (e.g. In Service, Completed)"""
        instance = self.get_object()
        
        # Check permission manually
        if instance.salon.owner != request.user and not request.user.is_superuser:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        
        old_status = instance.status
        # Create a mutable copy of the data to modify it
        data = request.data.copy() if hasattr(request.data, 'copy') else request.data.dict() if hasattr(request.data, 'dict') else dict(request.data)
        
        new_status = data.get('status')
        status_map = {
            'Waiting': 'pending',
            'In Service': 'in_progress',
            'completed': 'completed',
            'cancelled': 'cancelled'
        }
        
        if new_status in status_map:
            data['status'] = status_map[new_status]
        
        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Reload instance from DB to get updated status
        instance.refresh_from_db()
        
        # ── Queue Notifications ──
        
        # 1. Notify the current user if they are being served
        if instance.status == 'in_progress' and old_status != 'in_progress':
            Notification.objects.create(
                user=instance.user,
                title="Your turn is here!",
                message=f"Your service at {instance.salon.name} is starting now. Please proceed to the station.",
                notification_type='booking',
                link='/my-bookings'
            )
            
        # 2. Notify the NEXT person in line when someone is done or cancelled
        if instance.status in ['completed', 'cancelled'] and old_status not in ['completed', 'cancelled']:
            next_entry = SalonQueueEntry.objects.filter(
                salon=instance.salon,
                status='pending'
            ).order_by('joined_at').first()
            
            if next_entry:
                Notification.objects.create(
                    user=next_entry.user,
                    title="You are next!",
                    message=f"Someone just finished at {instance.salon.name}. You are now next in line! Please be ready.",
                    notification_type='booking',
                    link='/my-bookings'
                )
        
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='move-down')
    def move_down(self, request, pk=None):
        """Moves a customer one spot down in the waiting queue"""
        entry = self.get_object()
        
        # Security check: only salon owner can move people down
        if entry.salon.owner != request.user and not request.user.is_superuser:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        if entry.status != 'pending':
            return Response({"error": "Only waiting customers can be moved down"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Find the person immediately behind them
        next_person = SalonQueueEntry.objects.filter(
            salon=entry.salon,
            status='pending',
            joined_at__gt=entry.joined_at
        ).order_by('joined_at').first()

        if not next_person:
            return Response({"error": "Customer is already last in the waiting queue"}, status=status.HTTP_400_BAD_REQUEST)

        # Swap joined_at timestamps to swap positions
        with transaction.atomic():
            target_time = next_person.joined_at
            next_person.joined_at = entry.joined_at
            entry.joined_at = target_time
            
            entry.save()
            next_person.save()

        return Response({"message": "Customer moved down successfully"})

class SalonDashboardQueueView(APIView):
    """View for the Salon Owner Dashboard to see active queue"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        salon = SalonDataModel.objects.filter(owner=request.user).first()
        if not salon:
            return Response({"error": "No salon found"}, status=status.HTTP_404_NOT_FOUND)
        
        queue = SalonQueueEntry.objects.filter(
            salon=salon, 
            status__in=['pending', 'in_progress']
        ).order_by('joined_at')
        
        serializer = SalonQueueEntrySerializer(queue, many=True)
        return Response(serializer.data)

class SalonDashboardRecordsView(APIView):
    """View for the Salon Owner Dashboard to see history"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        salon = SalonDataModel.objects.filter(owner=request.user).first()
        if not salon:
            return Response({"error": "No salon found"}, status=status.HTTP_404_NOT_FOUND)
        
        records = SalonQueueEntry.objects.filter(
            salon=salon, 
            status='completed'
        ).order_by('-joined_at')[:20]
        
        serializer = SalonQueueEntrySerializer(records, many=True)
        return Response(serializer.data)

class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        # Validate that the service is completed before allowing a review
        queue_entry = serializer.validated_data.get('queue_entry')
        if queue_entry and queue_entry.status != 'completed':
            from rest_framework.exceptions import ValidationError
            raise ValidationError("You can only review a service after it has been completed.")
            
        serializer.save(user=self.request.user)


class SalonGalleryView(APIView):
    """List and upload gallery images for the owner's salon"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        salon = SalonDataModel.objects.filter(owner=request.user).first()
        if not salon:
            return Response({"error": "No salon found"}, status=status.HTTP_404_NOT_FOUND)
        images = SalonGallery.objects.filter(salon=salon)
        serializer = SalonGallerySerializer(images, many=True, context={'request': request})
        return Response(serializer.data)

    def post(self, request):
        salon = SalonDataModel.objects.filter(owner=request.user).first()
        if not salon:
            return Response({"error": "No salon found"}, status=status.HTTP_404_NOT_FOUND)
        image_file = request.FILES.get('image')
        if not image_file:
            return Response({"error": "No image provided"}, status=status.HTTP_400_BAD_REQUEST)
        gallery_image = SalonGallery.objects.create(salon=salon, image=image_file)
        serializer = SalonGallerySerializer(gallery_image, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class SalonGalleryDeleteView(APIView):
    """Delete a specific gallery image"""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            image = SalonGallery.objects.get(id=pk)
        except SalonGallery.DoesNotExist:
            return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)
        if image.salon.owner != request.user:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
        image.image.delete(save=False)  # delete from filesystem
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
