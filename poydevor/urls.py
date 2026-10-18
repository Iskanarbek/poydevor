"""
URL configuration for poydevor project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
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
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from poydevor import staff_panel
from poydevor.views import dashboard_redirect, home, internal_expire_orders, internal_setup
from wallet.admin_views import revenue_dashboard

urlpatterns = [
    # Our own staff panel — separate from Django's built-in /admin/ (kept
    # below for low-level data fixes, but staff use this one day to day).
    path('admin-panel/kirish/', staff_panel.staff_login, name='staff_login'),
    path('admin-panel/', staff_panel.staff_home, name='staff_home'),
    path('admin-panel/arxitektorlar/', staff_panel.architects_list, name='staff_architects_list'),
    path('admin-panel/arxitektorlar/<int:pk>/', staff_panel.architect_detail, name='staff_architect_detail'),
    path('admin-panel/arxitektorlar/<int:pk>/tasdiqlash/', staff_panel.architect_verify, name='staff_architect_verify'),
    path('admin-panel/arxitektorlar/<int:pk>/rad-etish/', staff_panel.architect_reject, name='staff_architect_reject'),
    path(
        'admin-panel/arxitektorlar/<int:pk>/royxat-tasdiqlash/',
        staff_panel.architect_approve_registration, name='staff_architect_approve_registration',
    ),
    path(
        'admin-panel/arxitektorlar/<int:pk>/royxat-rad-etish/',
        staff_panel.architect_reject_registration, name='staff_architect_reject_registration',
    ),
    path('admin-panel/daromad/', revenue_dashboard, name='revenue_dashboard'),
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('boshqaruv/', dashboard_redirect, name='dashboard'),
    path('internal/setup/', internal_setup, name='internal_setup'),
    path('internal/expire-orders/', internal_expire_orders, name='internal_expire_orders'),
    path('', include('accounts.urls')),
    path('', include('architects.urls')),
    path('', include('applications.urls')),
    path('', include('wallet.urls')),
    path('', include('offers.urls')),
    path('', include('reviews.urls')),
]

# Django normally only serves /media/ this way when DEBUG=True (this view
# isn't optimized for real production traffic). It's kept on unconditionally
# here because the committed media/ directory (the seeded demo photos) still
# needs to be readable in production, and Vercel's read-only filesystem means
# there's no separate process serving those files another way. New uploads
# don't hit this path at all when BLOB_READ_WRITE_TOKEN is set (see
# settings.py) — they go straight to Vercel Blob instead.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
