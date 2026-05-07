import io
import json
import os
import re
from functools import wraps

from django.core.files.base import ContentFile
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.middleware.csrf import get_token
from .models import Property, PropertyImage


def _to_webp(upload_file):
    """Convert any uploaded image to WebP using Pillow. Returns a ContentFile."""
    try:
        from PIL import Image
        img = Image.open(upload_file)
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGBA' if img.mode == 'P' else 'RGB')
        buf = io.BytesIO()
        img.save(buf, format='WEBP', quality=85)
        buf.seek(0)
        original_name = getattr(upload_file, 'name', 'image.jpg')
        base = os.path.splitext(original_name)[0]
        return ContentFile(buf.read(), name=f'{base}.webp')
    except Exception:
        upload_file.seek(0)
        return upload_file


# ── Server-side admin session guard ──
def admin_required(view_func):
    """Decorator that checks for a valid admin session before allowing access."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('is_admin'):
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


from django.core.paginator import Paginator


# ── Helper: resolve main_type from legacy property_type ──
_LEGACY_TO_MAIN = {
    'apartment': 'residential', 'villa': 'residential',
    'house': 'residential', 'penthouse': 'residential',
    'office': 'commercial', 'shop': 'commercial',
    'building': 'commercial', 'commercial': 'commercial',
    'land': 'land',
}
_SUB_TYPES = {'apartment', 'villa', 'house', 'penthouse', 'office', 'shop', 'building'}


def _resolve_main_type(prop):
    """Return effective main_type for a Property instance."""
    if prop.main_type:
        return prop.main_type
    return _LEGACY_TO_MAIN.get(prop.property_type, 'residential')


def _resolve_sub_type(prop):
    """Return effective sub_type for a Property instance."""
    if prop.sub_type:
        return prop.sub_type
    if prop.property_type in _SUB_TYPES:
        return prop.property_type
    return None


def _build_details_from_legacy(prop):
    """Build a details dict from legacy flat fields for backward compat display."""
    if prop.details:
        return prop.details
    d = {}
    main_type = _resolve_main_type(prop)
    # Only copy beds/baths for residential — commercial/land don't use them
    if main_type == 'residential':
        if prop.bedrooms is not None and prop.bedrooms > 0:
            d['bedrooms'] = prop.bedrooms
        if prop.bathrooms is not None and prop.bathrooms > 0:
            d['bathrooms'] = prop.bathrooms
    if prop.area:
        d['area'] = prop.area
    return d if d else None


def home_view(request):
    return render(request, 'BigDeals.html')


def pre_launch_view(request):
    return render(request, 'pre_launch.html')


def builder_projects_view(request):
    return render(request, 'builder_projects.html')


def buy_view(request):
    return render(request, 'buy.html')


def rent_view(request):
    return render(request, 'rent.html')


def commercial_view(request):
    return render(request, 'commercial.html')


def contact_view(request):
    return render(request, 'contact.html')



def api_properties(request):
    """
    JSON API for properties serving the frontend.
    Supports server-side pagination, search queries, main_type and sub_type filtering.
    """
    properties = Property.objects.filter(status='approved').prefetch_related('images')

    # 1. Type filter — supports both legacy sub_type names and new main_type
    prop_type = request.GET.get('type')
    if prop_type and prop_type != 'all':
        from django.db.models import Q
        if prop_type in ('residential', 'commercial', 'land'):
            # Filter by main_type OR legacy mapping
            legacy_keys = [k for k, v in _LEGACY_TO_MAIN.items() if v == prop_type]
            properties = properties.filter(
                Q(main_type=prop_type) | Q(property_type__in=legacy_keys)
            )
        else:
            # Filter by sub_type or legacy property_type (e.g. 'apartment')
            properties = properties.filter(
                Q(sub_type=prop_type) | Q(property_type=prop_type)
            )

    # 2. Text search
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        tokens = q.split()
        for token in tokens:
            properties = properties.filter(
                Q(title__icontains=token) | Q(location__icontains=token)
            )

    # 3. Handle Saved IDs
    ids_param = request.GET.get('ids')
    if ids_param:
        id_list = [_safe_int(x) for x in ids_param.split(',') if _safe_int(x)]
        properties = properties.filter(id__in=id_list)

    # 4. Paginator
    paginator = Paginator(properties, 12)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    prop_list = []
    for p in page_obj:
        main_type = _resolve_main_type(p)
        sub_type = _resolve_sub_type(p)
        details = _build_details_from_legacy(p)

        prop_list.append({
            'id': p.id,
            'title': p.title,
            'price': p.price,
            'location': p.location,
            # New schema fields
            'main_type': main_type,
            'sub_type': sub_type,
            'details': details,
            # Legacy compat fields (still used by card rendering, detail modal)
            'type': sub_type or main_type or p.property_type,
            'contactPhone': p.contact_number,
            'contactName': p.submitter_name,
            'contactEmail': p.contact_email,
            'beds': (details or {}).get('bedrooms', p.bedrooms) if main_type == 'residential' else None,
            'baths': (details or {}).get('bathrooms', p.bathrooms) if main_type == 'residential' else None,
            'area': (details or {}).get('area', p.area),
            'desc': p.description,
            'amenities': p.amenities,
            'videoUrl': p.video_url,
            'mapUrl': p.map_url,
            'verified': p.verified,
            'label': p.label,
            'status': p.status,
            'imageUrl': p.image.url if p.image else None,
            'gallery': [img.image.url for img in p.images.all() if img.image],
            'submittedAt': p.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })

    return JsonResponse({
        'properties': prop_list,
        'page': page_obj.number,
        'total_pages': paginator.num_pages,
        'has_next': page_obj.has_next()
    })


def admin_dashboard_view(request):
    properties = list(Property.objects.all().prefetch_related('images'))

    total = len(properties)
    approved = len([p for p in properties if p.status == 'approved'])
    pending = len([p for p in properties if p.status == 'pending'])
    rejected = len([p for p in properties if p.status == 'rejected'])

    context = {
        'properties': properties,
        'total': total,
        'approved': approved,
        'pending': pending,
        'rejected': rejected,
        'admin_password': os.getenv('ADMIN_PASSWORD', 'bigdeals2025'),
    }
    return render(request, 'admin.html', context)


def admin_login(request):
    """Server-side login endpoint — sets session on correct password."""
    if request.method == 'POST':
        password = request.POST.get('password', '')
        expected = os.getenv('ADMIN_PASSWORD', 'bigdeals2025')
        if password == expected:
            request.session['is_admin'] = True
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Invalid password'}, status=401)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


def admin_logout(request):
    """Server-side logout endpoint — clears admin session."""
    request.session.pop('is_admin', None)
    return JsonResponse({'success': True})


# ── Helper: parse numeric price from display string ──
def _parse_price_value(price_str):
    if not price_str:
        return None
    cleaned = re.sub(r'[₹,\s]', '', price_str)
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


# ── Helper: safe int parse ──
def _safe_int(value):
    if not value:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def add_property(request):
    """Handles both public user submissions and admin add/edit.
    Accepts new schema fields (main_type, sub_type, details JSON) as well as
    legacy flat fields for backward compatibility.
    """
    if request.method == 'POST':
        property_id = request.POST.get('property_id')
        title = (request.POST.get('title') or '')[:255]
        location = (request.POST.get('location') or '')[:255]
        price = (request.POST.get('price') or '')[:50]
        contact = (request.POST.get('contact') or '')[:20]
        email = request.POST.get('email') or ''
        name = (request.POST.get('name') or '')[:255]

        # ── NEW: schema-driven type fields ──
        main_type = (request.POST.get('main_type') or '').strip().lower() or None
        sub_type = (request.POST.get('sub_type') or '').strip().lower() or None
        details_raw = request.POST.get('details') or ''
        try:
            details = json.loads(details_raw) if details_raw else None
        except (json.JSONDecodeError, TypeError):
            details = None

        # ── LEGACY: derive property_type from sub_type / main_type for backward compat ──
        if sub_type:
            property_type = sub_type
        elif main_type:
            # For land and commercial (no subtype), use main_type directly
            property_type = main_type
        else:
            # Fallback to old field
            property_type = (request.POST.get('property_type') or 'apartment')[:50].lower()

        # ── LEGACY flat fields (still accepted from admin form + old clients) ──
        beds = _safe_int(request.POST.get('beds'))
        baths = _safe_int(request.POST.get('baths'))
        area = (request.POST.get('area') or '')[:100]
        desc = request.POST.get('desc') or ''
        amenities = request.POST.get('amenities') or ''
        video = request.POST.get('video') or ''
        map_url = request.POST.get('map_url') or ''
        verified = request.POST.get('verified') == 'true'
        label = request.POST.get('label')
        if label == 'none':
            label = None

        # If we got a details JSON, extract beds/baths/area from it for the
        # legacy columns so existing display code still works
        if details:
            if beds is None and 'bedrooms' in details:
                beds = _safe_int(details['bedrooms'])
            if baths is None and 'bathrooms' in details:
                baths = _safe_int(details['bathrooms'])
            if not area and 'area' in details:
                area = str(details['area'])
            if not area and 'plot_size' in details:
                area = str(details['plot_size'])

        cover_index = request.POST.get('cover_index')
        cover_db_id = request.POST.get('cover_db_id')

        images = request.FILES.getlist('images')
        image = request.FILES.get('image')

        # Validate required fields
        if not title or not location or not price:
            return redirect('custom-admin')

        # Validate file uploads
        ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
        MAX_SIZE = 10 * 1024 * 1024  # 10MB

        price_value = _parse_price_value(price)

        if property_id:
            try:
                prop = Property.objects.get(pk=property_id)
                prop.title = title
                prop.location = location
                prop.property_type = property_type
                prop.main_type = main_type
                prop.sub_type = sub_type
                if details is not None:
                    prop.details = details
                prop.price = price
                prop.price_value = price_value
                prop.contact_number = contact
                if name:
                    prop.submitter_name = name
                if email:
                    prop.contact_email = email
                if beds is not None:
                    prop.bedrooms = beds
                if baths is not None:
                    prop.bathrooms = baths
                if area:
                    prop.area = area
                if desc:
                    prop.description = desc
                if amenities:
                    prop.amenities = amenities
                if video:
                    prop.video_url = video
                if map_url:
                    prop.map_url = map_url

                prop.verified = verified
                prop.label = label

                if image:
                    if prop.image:
                        prop.image.delete(save=False)
                    prop.image = _to_webp(image)

                prop.save()
            except Property.DoesNotExist:
                prop = None
        else:
            prop = Property.objects.create(
                title=title,
                location=location,
                property_type=property_type,
                main_type=main_type,
                sub_type=sub_type,
                details=details,
                price=price,
                price_value=price_value,
                contact_number=contact,
                contact_email=email or None,
                submitter_name=name or None,
                bedrooms=beds,
                bathrooms=baths,
                area=area or None,
                description=desc or None,
                amenities=amenities or None,
                video_url=video or None,
                map_url=map_url or None,
                verified=verified,
                label=label,
                status='pending',
                image=_to_webp(image) if image else None
            )

        # Process deferred image deletions
        deleted_images_str = request.POST.get('deleted_images', '')
        if deleted_images_str and prop:
            for img_id in deleted_images_str.split(','):
                try:
                    img_to_delete = PropertyImage.objects.get(id=img_id, property=prop)
                    img_to_delete.image.delete(save=False)
                    img_to_delete.delete()
                except PropertyImage.DoesNotExist:
                    pass

        # Process multi-upload images
        if prop:
            all_images = images if images else (request.FILES.getlist('image') or [])
            new_cover = None

            for idx, img in enumerate(all_images):
                if img.content_type not in ALLOWED_TYPES or img.size > MAX_SIZE:
                    continue
                prop_img = PropertyImage.objects.create(property=prop, image=_to_webp(img))
                if str(cover_index) == str(idx):
                    new_cover = prop_img.image

            if cover_db_id:
                try:
                    db_img = PropertyImage.objects.get(id=cover_db_id)
                    new_cover = db_img.image
                except PropertyImage.DoesNotExist:
                    pass

            if new_cover:
                if prop.image:
                    prop.image.delete(save=False)
                prop.image = new_cover
                prop.save()
            elif not prop.image:
                first_img = prop.images.first()
                if first_img:
                    prop.image = first_img.image
                    prop.save()

        return redirect('custom-admin')
    return redirect('custom-admin')


@admin_required
def update_property_status(request, pk):
    if request.method == 'POST':
        try:
            prop = Property.objects.get(pk=pk)
            status = request.POST.get('status')
            if status in dict(Property.STATUS_CHOICES):
                prop.status = status
                prop.save(update_fields=['status'])
                return JsonResponse({'success': True, 'id': pk, 'status': status})
            return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
        except Property.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)


@admin_required
def delete_image(request, pk):
    if request.method in ('POST', 'DELETE'):
        try:
            image = PropertyImage.objects.get(pk=pk)
            image.image.delete(save=False)
            image.delete()
            return JsonResponse({'success': True})
        except PropertyImage.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Image not found'}, status=404)
    return JsonResponse({'success': False}, status=400)


@admin_required
def delete_property(request, pk):
    if request.method in ('POST', 'DELETE'):
        try:
            prop = Property.objects.get(pk=pk)
            for img in prop.images.all():
                img.image.delete(save=False)
            if prop.image:
                prop.image.delete(save=False)
            prop.delete()
            return JsonResponse({'success': True})
        except Property.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Property not found'}, status=404)
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=400)
