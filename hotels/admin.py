from django.contrib import admin
from django.utils.html import format_html
from hotels.models import (
    HotelDataModel, Booking, Room, NearbyAttraction,
    Coupon, HotelGallery, Review, ReviewImage
)


class RoomInline(admin.TabularInline):
    model = Room
    extra = 1
    fields = ('room_type', 'price', 'adults', 'children', 'total_rooms')


class HotelGalleryInline(admin.TabularInline):
    model = HotelGallery
    extra = 1


class NearbyAttractionInline(admin.TabularInline):
    model = NearbyAttraction
    extra = 1


@admin.register(HotelDataModel)
class HotelAdmin(admin.ModelAdmin):
    list_display = ('image_preview', 'name', 'city', 'area', 'badge', 'price', 'owner')
    search_fields = ('name', 'city', 'area', 'owner__email')
    list_filter = ('city', 'badge')
    readonly_fields = ('image_preview',)
    inlines = [RoomInline, HotelGalleryInline, NearbyAttractionInline]

    fieldsets = (
        ('Basic Info', {
            'fields': ('owner', 'name', 'city', 'area', 'badge', 'description')
        }),
        ('Pricing', {
            'fields': ('price', 'old_price')
        }),
        ('Location', {
            'fields': ('latitude', 'longitude', 'keywords'),
        }),
        ('Images', {
            'fields': ('image', 'room_image1', 'room_image2', 'environment_image', 'image_preview'),
        }),
        ('Amenities', {
            'fields': ('amenities',),
            'classes': ('collapse',),
        }),
    )

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="60" height="60" style="object-fit:cover; border-radius:6px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Preview'


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'room_type', 'price', 'adults', 'total_rooms')
    list_filter = ('hotel', 'room_type')
    search_fields = ('hotel__name', 'room_type')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'hotel', 'status', 'payment_status', 'rooms_booked', 'check_in', 'check_out', 'created_at')
    list_filter = ('status', 'payment_status', 'check_in', 'hotel')
    search_fields = ('user__email', 'user__first_name', 'hotel__name', 'razorpay_order_id')
    date_hierarchy = 'check_in'
    readonly_fields = ('created_at', 'razorpay_order_id')

    fieldsets = (
        ('Booking Info', {
            'fields': ('user', 'hotel', 'room', 'check_in', 'check_out', 'rooms_booked', 'number_of_guests')
        }),
        ('Status & Payment', {
            'fields': ('status', 'payment_status', 'razorpay_order_id', 'final_price', 'room_type_name')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(hotel__owner=request.user)


@admin.register(HotelGallery)
class HotelGalleryAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'image_preview')
    search_fields = ('hotel__name',)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="60" height="60" style="object-fit: cover; border-radius: 4px;" />',
                obj.image.url
            )
        return "No image"
    image_preview.short_description = 'Preview'


@admin.register(NearbyAttraction)
class NearbyAttractionAdmin(admin.ModelAdmin):
    list_display = ('hotel', 'name', 'distance_km')
    search_fields = ('hotel__name', 'name')


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'hotel', 'discount_percent', 'is_active', 'valid_from', 'valid_to')
    list_filter = ('is_active', 'hotel')
    search_fields = ('code', 'hotel__name')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'hotel', 'rating', 'created_at')
    list_filter = ('rating', 'hotel', 'created_at')
    search_fields = ('user__email', 'hotel__name', 'comment')
    readonly_fields = ('created_at',)


@admin.register(ReviewImage)
class ReviewImageAdmin(admin.ModelAdmin):
    list_display = ('review',)
    search_fields = ('review__hotel__name',)