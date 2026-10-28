from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

admin.site.site_header = "Ishxona boshqaruv paneli"
admin.site.site_title = "Ishxona"
admin.site.index_title = "Boshqaruv"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/admin/", permanent=False)),
]
