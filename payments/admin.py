from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('razorpay_order_id', 'razorpay_payment_id', 'user', 'amount', 'status', 'content_type', 'object_id', 'created_at')
    list_filter = ('status', 'content_type', 'created_at')
    search_fields = ('razorpay_order_id', 'razorpay_payment_id', 'user__email')
    readonly_fields = ('created_at', 'updated_at', 'content_type', 'object_id', 'content_object', 'razorpay_order_id')
    date_hierarchy = 'created_at'

    fieldsets = (
        ('User & Amount', {
            'fields': ('user', 'amount', 'currency')
        }),
        ('Razorpay Details', {
            'fields': ('razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature', 'status')
        }),
        ('Linked Booking', {
            'fields': ('content_type', 'object_id', 'content_object'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
