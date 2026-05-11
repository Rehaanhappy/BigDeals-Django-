from django.db import models


class Property(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    # Legacy flat type (kept for backward compat with existing data & search chips)
    TYPE_CHOICES = [
        ('apartment', 'Apartment'),
        ('villa', 'Villa'),
        ('house', 'House'),
        ('land', 'Land'),
        ('commercial', 'Commercial'),
        ('penthouse', 'Penthouse'),
        ('other', 'Other'),
        # New main-type values (used when sub_type is absent)
        ('residential', 'Residential'),
        ('office', 'Office'),
        ('shop', 'Shop'),
        ('building', 'Building'),
    ]

    # ── NEW: schema-driven type system ──
    MAIN_TYPE_CHOICES = [
        ('residential', 'Residential'),
        ('commercial', 'Commercial'),
        ('land', 'Land'),
    ]

    main_type = models.CharField(
        max_length=20,
        choices=MAIN_TYPE_CHOICES,
        null=True, blank=True,
        db_index=True,
        help_text='Top-level category: residential / commercial / land'
    )
    sub_type = models.CharField(
        max_length=50,
        null=True, blank=True,
        db_index=True,
        help_text='Subtype: apartment, villa, house, office, shop, building'
    )
    details = models.JSONField(
        null=True, blank=True,
        help_text='Flexible JSON bag of type-specific fields (bedrooms, area, furnishing, etc.)'
    )

    # ── EXISTING FIELDS (unchanged) ──
    title = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    property_type = models.CharField(max_length=50, choices=TYPE_CHOICES, default='apartment')
    price = models.CharField(max_length=50)
    price_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                      help_text='Numeric price for sorting/filtering')
    contact_number = models.CharField(max_length=20)
    contact_email = models.EmailField(max_length=255, null=True, blank=True)
    submitter_name = models.CharField(max_length=255, null=True, blank=True)

    # Detailed metadata (kept for backward compat; new submissions use details JSON)
    bedrooms = models.IntegerField(null=True, blank=True)
    bathrooms = models.IntegerField(null=True, blank=True)
    area = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    amenities = models.TextField(null=True, blank=True)
    video_url = models.URLField(max_length=500, null=True, blank=True)
    map_url = models.URLField(max_length=1000, null=True, blank=True)

    verified = models.BooleanField(default=False)
    label = models.CharField(max_length=50, null=True, blank=True)

    # Which listing pages this property is tagged to appear on.
    # Stored as a JSON list of slug strings, e.g. ["buy", "rent"].
    # Valid values: 'buy', 'rent', 'commercial', 'pre_launch', 'builder_projects'
    placements = models.JSONField(
        default=list,
        blank=True,
        help_text="Page slugs this property is tagged for: buy, rent, commercial, pre_launch, builder_projects"
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    image = models.ImageField(upload_to='property_images/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name_plural = 'Properties'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    # Convenience: resolve effective main_type from legacy property_type
    def get_main_type(self):
        if self.main_type:
            return self.main_type
        legacy_map = {
            'apartment': 'residential', 'villa': 'residential',
            'house': 'residential', 'penthouse': 'residential',
            'office': 'commercial', 'shop': 'commercial',
            'building': 'commercial', 'commercial': 'commercial',
            'land': 'land',
        }
        return legacy_map.get(self.property_type, 'residential')

    def get_sub_type(self):
        if self.sub_type:
            return self.sub_type
        sub_types = {'apartment', 'villa', 'house', 'penthouse', 'office', 'shop', 'building'}
        if self.property_type in sub_types:
            return self.property_type
        return None


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='property_images/')

    def __str__(self):
        return f"{self.property.title} Image"
