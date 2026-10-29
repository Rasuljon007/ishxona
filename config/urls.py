from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import RedirectView

from core import views

admin.site.site_header = "Ishxona boshqaruv paneli"
admin.site.site_title = "Ishxona"
admin.site.index_title = "Boshqaruv"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sardor/", views.dashboard, name="dashboard"),
    path("sardor/kirish/", views.LoginView.as_view(), name="login"),
    path("sardor/chiqish/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("sardor/tasdiqlash/", views.approve, name="approve"),
    path("sardor/hammasini-tasdiqlash/", views.approve_all, name="approve_all"),
    path("sardor/rad-etish/", views.reject, name="reject"),
    path("sardor/tahrirlash/", views.edit, name="edit"),
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
]
