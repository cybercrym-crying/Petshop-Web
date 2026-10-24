from django.core.management.base import BaseCommand

from common.dark_css import BASE_DIR, build


class Command(BaseCommand):
    help = "Membuat ulang file CSS mode gelap (*-dark.css) untuk halaman pelanggan dan landing."

    def handle(self, *args, **options):
        for path, content in build().items():
            path.write_text(content, encoding="utf-8")
            self.stdout.write(str(path.relative_to(BASE_DIR)))
