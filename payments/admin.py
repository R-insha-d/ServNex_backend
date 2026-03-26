from django.contrib import admin
from .models import Payment

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'razorpay_order_id', 'razorpay_payment_id', 'user', 
        'amount', 'status', 'content_type', 'object_id', 'created_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = ('razorpay_order_id', 'razorpay_payment_id', 'user__email')
