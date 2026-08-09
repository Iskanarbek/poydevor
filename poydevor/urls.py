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

from poydevor.views import dashboard_redirect, home, internal_setup

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('boshqaruv/', dashboard_redirect, name='dashboard'),
    path('internal/setup/', internal_setup, name='internal_setup'),
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
