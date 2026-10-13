from django.core.management.base import BaseCommand
from django.db.models import Case, F, IntegerField, Sum, When

from product.models import MutationType, Product, StockMutation


class Command(BaseCommand):
    help = "Bandingkan Product.stock dengan total riwayat StockMutation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Catat mutasi penyesuaian agar riwayat sama dengan stok saat ini "
            "(stok produk tidak diubah).",
        )

    def handle(self, *args, **options):
        signed = Case(
            When(mutations__mutationType=MutationType.IN, then="mutations__quantity"),
            When(
                mutations__mutationType=MutationType.OUT,
                then=-1 * F("mutations__quantity"),
            ),
            default=0,
            output_field=IntegerField(),
        )
        mismatches = 0
        for product in Product.objects.annotate(ledger=Sum(signed)).order_by("pk"):
            ledger = product.ledger or 0
            diff = product.stock - ledger
            if diff == 0:
                continue
            mismatches += 1
            self.stdout.write(
                f"#{product.pk} {product.name}: stok={product.stock} "
                f"riwayat={ledger} selisih={diff:+d}"
            )
            if options["fix"]:
                StockMutation.objects.create(
                    product=product,
                    mutationType=MutationType.IN if diff > 0 else MutationType.OUT,
                    quantity=abs(diff),
                    note="Penyesuaian audit stok",
                )
        if mismatches == 0:
            self.stdout.write(self.style.SUCCESS("Stok dan riwayat mutasi cocok."))
        elif options["fix"]:
            self.stdout.write(self.style.WARNING(f"{mismatches} produk disesuaikan."))
        else:
            self.stdout.write(
                self.style.WARNING(f"{mismatches} produk selisih. Jalankan --fix.")
            )
