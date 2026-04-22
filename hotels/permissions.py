from rest_framework import permissions

class IsHotelOwnerOrReadOnly(permissions.BasePermission):
    """Allows only the hotel owner to edit/delete rooms, galleries, etc."""
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        # The object (Room, Gallery, etc.) must have a foreign key to hotel
        return obj.hotel and obj.hotel.owner == request.user

class IsReviewOwnerOrReadOnly(permissions.BasePermission):
    """Allows only the author of the review to edit/delete it."""
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.user == request.user
