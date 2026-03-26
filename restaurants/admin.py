from django.contrib import admin
from .models import RestaurantDataModel, TableReservation, Review, ReviewImage


@admin.register(RestaurantDataModel)
class RestaurantAdmin(admin.ModelAdmin):
    list_display = ['name', 'city', 'area', 'badge', 'cuisine_type', 'price_range', 'rating', 'total_tables']
    list_filter = ['badge', 'city', 'price_range', 'cuisine_type']
    search_fields = ['name', 'city', 'area', 'description']
    readonly_fields = ['id', 'total_tables', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'city', 'area', 'badge', 'cuisine_type', 'price_range')
        }),
        ('Pricing & Capacity', {
            'fields': ('average_cost_for_two', 'total_tables')
        }),
        ('Details', {
            'fields': ('description', 'rating')
        }),
        ('Images', {
            'fields': ('image', 'menu_image', 'interior_image')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TableReservation)
class TableReservationAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'restaurant', 'reservation_date', 'reservation_time', 'status', 'payment_status', 'created_at']
    list_filter = ['status', 'payment_status', 'reservation_date', 'restaurant']
    search_fields = ['user__email', 'user__first_name', 'restaurant__name', 'razorpay_order_id']
    readonly_fields = ['created_at', 'tables_reserved']
    date_hierarchy = 'reservation_date'
    
    fieldsets = (
        ('Reservation Details', {
            'fields': ('user', 'restaurant', 'reservation_date', 'reservation_time')
        }),
        ('Guest Information', {
            'fields': ('number_of_guests', 'tables_reserved', 'special_requests')
        }),
        ('Payment & Status', {
            'fields': ('status', 'payment_status', 'razorpay_order_id', 'created_at')
        }),
    )

@admin.register(Review)
class RestaurantReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'restaurant', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')

admin.site.register(ReviewImage)
