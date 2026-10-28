import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "ADMIN_USERNAME va ADMIN_PASSWORD bo'yicha boshliq uchun admin hisobini yaratadi (agar yo'q bo'lsa)."

    def handle(self, *args, **options):
        username = os.environ["ADMIN_USERNAME"]
        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write("Admin hisobi allaqachon bor.")
            return
        User.objects.create_superuser(username=username, password=os.environ["ADMIN_PASSWORD"])
        self.stdout.write(f"Admin hisobi yaratildi: {username}")
