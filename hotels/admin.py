from django.contrib import admin
from hotels.models import (
    HotelDataModel, Booking, Room, NearbyAttraction, 
    Coupon, HotelGallery, Review, ReviewImage
)
from django.utils.html import format_html

class HotelAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'price', 'badge', 'owner', 'image_preview')
    search_fields = ('name', 'city')
    list_filter = ('city', 'badge')

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" style="object-fit: cover; border-radius: 4px;"/>', obj.image.url)
        return "No image"
    image_preview.short_description = 'Preview'

class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'hotel', 'status', 'payment_status', 'final_price', 'check_in')
    list_filter = ('status', 'payment_status', 'check_in', 'hotel')
    search_fields = ('user__email', 'hotel__name', 'razorpay_order_id')
    date_hierarchy = 'check_in'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(hotel__owner=request.user)

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'hotel', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')

admin.site.register(HotelDataModel, HotelAdmin)
admin.site.register(Booking, BookingAdmin)
admin.site.register(Room)
admin.site.register(NearbyAttraction)
admin.site.register(Coupon)
admin.site.register(HotelGallery)
admin.site.register(ReviewImage)