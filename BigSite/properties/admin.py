from django.contrib import admin
from .models import Property

@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('title', 'location', 'property_type', 'price', 'status', 'created_at')
    list_filter = ('status', 'property_type')
    search_fields = ('title', 'location', 'contact_number')
