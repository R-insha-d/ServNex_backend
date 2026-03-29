from django.contrib import admin
from django.utils.html import format_html
from .models import RestaurantDataModel, TableReservation, Review, ReviewImage


@admin.register(RestaurantDataModel)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ('image_preview', 'name', 'city', 'area', 'badge', 'cuisine_type', 'price_range', 'total_tables', 'owner')
    list_filter = ('badge', 'city', 'price_range', 'cuisine_type')
    search_fields = ('name', 'city', 'area', 'owner__email')
    readonly_fields = ('id', 'total_tables', 'created_at', 'updated_at', 'image_preview')

    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'city', 'area', 'badge', 'cuisine_type', 'price_range')
        }),
        ('Pricing & Table Capacity', {
            'fields': ('average_cost_for_two', 'tables_4_capacity', 'tables_6_capacity', 'tables_8_capacity', 'tables_10_capacity')
        }),
        ('Details', {
            'fields': ('description', 'rating', 'keywords')
        }),
        ('Location', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        }),
        ('Operational Hours', {
            'fields': ('opening_time', 'closing_time', 'is_open'),
        }),
        ('Images', {
            'fields': ('image', 'menu_image', 'interior_image', 'image_preview'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
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


@admin.register(TableReservation)
class TableReservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'restaurant', 'reservation_date', 'reservation_time', 'number_of_guests', 'status', 'payment_status', 'created_at')
    list_filter = ('status', 'payment_status', 'reservation_date', 'restaurant')
    search_fields = ('user__email', 'user__first_name', 'restaurant__name', 'razorpay_order_id')
    readonly_fields = ('created_at', 'tables_reserved', 'table_capacity')
    date_hierarchy = 'reservation_date'

    fieldsets = (
        ('Reservation Details', {
            'fields': ('user', 'restaurant', 'reservation_date', 'reservation_time')
        }),
        ('Guest Information', {
            'fields': ('number_of_guests', 'table_capacity', 'tables_reserved', 'special_requests')
        }),
        ('Payment & Status', {
            'fields': ('status', 'payment_status', 'razorpay_order_id', 'created_at')
        }),
    )


@admin.register(Review)
class RestaurantReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'restaurant', 'rating', 'created_at')
    list_filter = ('rating', 'restaurant', 'created_at')
    search_fields = ('user__email', 'restaurant__name', 'comment')
    readonly_fields = ('created_at',)


@admin.register(ReviewImage)
class ReviewImageAdmin(admin.ModelAdmin):
    list_display = ('review',)
    search_fields = ('review__restaurant__name',)
