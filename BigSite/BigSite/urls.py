"""
URL configuration for BigSite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from properties.views import (
    home_view, admin_dashboard_view, add_property,
    update_property_status, delete_image, delete_property,
    admin_login, admin_logout, api_properties,
    pre_launch_view, builder_projects_view,
    buy_view, rent_view, commercial_view, contact_view
)

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('pre_launch.html', pre_launch_view, name='pre_launch'),
    path('builder_projects.html', builder_projects_view, name='builder_projects'),
    path('buy/', buy_view, name='buy'),
    path('rent/', rent_view, name='rent'),
    path('commercial/', commercial_view, name='commercial'),
    path('contact/', contact_view, name='contact'),
    path('api/properties/', api_properties, name='api-properties'),
    path('admin/', admin_dashboard_view, name='custom-admin'),
    path('admin/login/', admin_login, name='admin-login'),
    path('admin/logout/', admin_logout, name='admin-logout'),
    path('admin/add/', add_property, name='add-property'),
    path('admin/update/<int:pk>/', update_property_status, name='update-property'),
    path('admin/delete/<int:pk>/', delete_property, name='delete-property'),
    path('admin/delete-image/<int:pk>/', delete_image, name='delete-image'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
