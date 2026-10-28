# Seelly Petshop

Aplikasi web toko hewan peliharaan: katalog dan pemesanan online, kasir (POS),
pengiriman oleh kurir dengan rute otomatis dan pelacakan realtime di peta,
layanan grooming bertahap dengan antrean dan antar-jemput hewan, chatbot FAQ,
serta dasbor admin. Hanya web (desktop & HP), tanpa layanan berbayar.
Tersedia dalam Bahasa Indonesia dan Inggris (tombol **ID/EN** di setiap menu).

## Alur halaman

Pengunjung membuka beranda (landing) → **Masuk** → diarahkan ke dasbor sesuai
peran. Yang bisa mendaftar sendiri hanya **pelanggan** (`/daftar`) dan **kurir**
(`/daftar/staf`, aktif setelah disetujui admin). Staf lain (kasir, groomer) hanya
dibuat Admin/Super Admin lewat Kelola Akun → Tambah Pegawai.

## Peran

| Peran | Yang bisa dilakukan |
| --- | --- |
| Pengunjung | Katalog, cari & filter, favorit, keranjang, pesan lewat WhatsApp tanpa akun, lacak resi, chatbot FAQ, daftar akun |
| Pelanggan | Checkout di situs dengan titik peta (ongkir per km), bayar transfer (foto bukti lewat kamera) atau COD, batas bayar transfer 24 jam, **peta lacak sejak pesanan dibuat (toko → rumah) dan posisi kurir realtime saat diantar**, QR serah-terima, ulasan & komplain; booking grooming dengan profil hewan, QR check-in, pantau antrean & foto tiap tahap, minta jemput/antar hewan dan pantau kurirnya di peta, pengingat grooming |
| Kasir | **Transaksi offline (kasir)**: buka/tutup shift dengan modal & rekap selisih, scan kode barang (scanner USB/kamera) atau QR booking, pembeli tanpa akun, dibawa langsung atau diantar kurir, bayar tunai (kembalian otomatis)/transfer/QRIS statis/campuran, diskon dengan alasan, parkir transaksi, struk 58 mm/A4 + kirim WA + struk digital lewat QR, ajukan retur; juga cek & setujui bukti transfer, antrean packing + label QR, terima setoran COD kurir, check-in hewan (scan QR) & papan antrean, booking layanan, komplain |
| Groomer | Antrean hari ini, kerjakan tahap demi tahap dengan foto kamera (tahap wajib foto tidak bisa dilewati) |
| Kurir | Rute otomatis terdekat → terjauh dengan peta realtime, fitur terkunci selama GPS mati, scan QR label untuk mengambil paket, scan QR pelanggan + foto saat serah terima, laporan kendala, setoran COD; semua kurir juga bisa mendapat tugas antar-jemput hewan (kandang/boks disediakan toko); **satu tugas sekaligus**: selama antar-jemput hewan kurir tidak bisa mengambil/menerima paket, dan kurir yang masih membawa paket tidak bisa berangkat menjemput hewan |
| Admin | Semua fitur kasir + batalkan transaksi kasir (stok kembali, tercatat), setujui/tolak retur, diskon di atas batas kasir, Laporan Kasir (per metode bayar, per kasir, online vs offline, shift, CSV), kode barang & label QR, dasbor Ringkasan Toko (CSV), produk, stok & harga, akun pegawai/pelanggan, persetujuan staf, layanan & tahapannya, FAQ, Pengaturan Toko (alamat & titik peta toko, tarif ongkir, rekening, jam buka, batas bayar). **Tidak bisa membuat/mengubah akun admin** |
| Super Admin | Semua fitur admin + membuat dan mengelola akun admin, akses `/admin/` |

Setiap aksi penting tercatat di log aktivitas, dan setiap peran mendapat
notifikasi (ikon lonceng) untuk hal yang perlu ditindaklanjuti.

### Tampilan dasbor

Semua dasbor memakai pola yang sama: **yang perlu dikerjakan ada di atas**, angka
diberi pembanding, dan warna ungu hanya untuk tombol aksi. Gaya bersama ada di
`static/css/ui.css` (+ `static/js/ui.js` untuk tinggi/lebar batang grafik).

- **Admin** (`/staff/admin/dashboard`): tombol Buka kasir dan Tambah produk di kepala
  halaman; kotak-kotak "Perlu tindakan sekarang" (bukti transfer, pesanan baru, packing,
  setoran COD, retur, komplain, stok, pendaftar staf) yang hanya muncul bila ada isinya,
  warna kotak menurut tingkat mendesak; 4 angka utama dengan ▲/▼ dibanding periode
  sebelumnya yang sama panjang; grafik penjualan kasir vs online dengan kolom samping
  "Kasir sekarang" dan "Kurir sekarang" (tiap kurir: antar-jemput hewan, antar paket
  berapa, atau siap); produk terlaris, stok perlu diisi, booking hari ini, pesanan terbaru.
- **Kasir** (`/staff/kasir/`, halaman awal kasir setelah masuk): status shift dan
  uang di laci, tombol buka layar kasir, pekerjaan yang menunggu, struk terakhir,
  booking hari ini.
- **Kurir** (HP dulu): tujuan berikutnya di urutan pertama (progres, tagihan tunai,
  tombol serah terima), lalu peta rute, lalu urutan antar berikutnya. Di layar lebar
  peta di kiri, tujuan dan urutan di kanan. Riwayat berupa baris yang bisa diketuk
  (nama, nomor, waktu, status).
- **Groomer** (HP dulu): tiga angka antrean, pekerjaan yang sedang berjalan beserta
  tahapnya, lalu antrean berikutnya dalam kartu ringkas (layanan, check-in, berat,
  pemilik, harga dalam satu baris; kondisi dan catatan pemilik ditandai). Hanya
  antrean pertama yang bertombol ungu penuh supaya urutan antrean diikuti.
- **Pelanggan** (HP dulu): empat kotak aksi cepat (Belanja, Booking grooming, Hewan saya,
  Lacak resi), pengiriman yang sedang berjalan dengan peta, tagihan transfer yang menunggu
  (tombol Bayar langsung ke halaman kirim bukti; rincian rekening dilipat dan dibuka bila
  perlu), langkah pesanan mendatar, lalu booking, hewan beserta pengingat grooming, dan
  notifikasi. Di daftar pesanan, nomor resi turun ke baris sendiri di HP.
- **Landing page**: hero, empat keunggulan (2x2 ringkas di HP), bagian "Cara memesan"
  empat langkah (daftar, pilih produk/jadwal, bayar tunai atau transfer, pantau kurir),
  kategori, produk terlaris dan layanan dari data nyata, lalu "Kunjungi toko" yang
  mengambil alamat, jam buka, dan WhatsApp dari Pengaturan Toko.

**Palet Seelly** (satu untuk semua peran): ungu `#6b21a8` untuk merek dan tombol aksi,
latar `#f7f5fa`, garis `#eadcf4`, teks `#261a33`, amber `#f59e0b` hanya untuk sorotan
(angka di menu). Token ada di `static/css/ui.css` (`--ui-*`),
`account/css/staff_sidebar.css` (`--ss-*`) dan `static/css/actions.css` (`--action`).
Halaman staf lama yang masih memakai warna `--t-*` diarahkan ke palet ini di
`account/css/staff_theme.css` (blok `:root`), mode gelapnya di blok `html[data-theme="dark"]`.
Menu samping staf menampilkan merek Seelly, nama dan peran pengguna, dan untuk peran
Kasir juga status kasir (buka sejak jam berapa / belum dibuka, menuju Kas & Shift).

**Layar kasir** (`/staff/admin/make_transaction/`): scan atau cari di atas, tagihan
grooming dan transaksi parkir di bawahnya, chip kategori (`?cat=`), lalu kartu produk.
Keranjang di kanan memakai tombol − / + (kolom angka tetap bisa diketik; 0 = hapus).
Kolom pembeli, diskon dan pembayaran baru muncul setelah ada barang. Total dan tombol
"Bayar Rp …" menempel di bawah panel keranjang; di HP total + Bayar menempel di bawah layar.

Ikon (Bootstrap Icons, Font Awesome), huruf, dan Bootstrap disimpan di
`static/vendor/` sehingga tampilan tetap utuh saat internet toko lambat; hanya
peta yang butuh internet. Warna tombol aksi diatur satu tempat di
`static/css/actions.css` (ungu = aksi, hijau = selesai/WhatsApp, merah = berbahaya).
Teks bawaan Django yang belum berbahasa Indonesia diterjemahkan di
`locale/id/LC_MESSAGES/django.po`.

Landing page (`/`, Belanja, Layanan, Tentang Kami) hanya untuk pengunjung.
Pelanggan yang sudah masuk langsung dibawa ke `/dasbor/` dan memakai **area
pelanggan** sendiri: bilah atas ringkas, menu samping (Dasbor, Belanja,
Keranjang, Pesanan, Favorit, Lacak, Booking, Hewan, Notifikasi, Komplain, Akun),
dan di HP menu bawah + laci menu (`customer/_app_nav.html`, `_app_side.html`,
`customer/css/app.css`). Staf yang membuka situs tetap melihat tampilan publik.

Di HP (lebar ≤ 720 px), tabel bertanda `data-stack` tampil sebagai kartu; label
tiap baris diisi otomatis dari judul kolom oleh `static/js/layout.js`. Semua
halaman memakai satu huruf (Plus Jakarta Sans) dan teks terkecil 12 px.

## Stack

- Python 3.12+ (diuji di 3.13), Django 6.1, Pillow, qrcode
- SQLite (bawaan Django)
- Template Django + CSS/JS biasa. Bootstrap, Leaflet (peta) dan jsQR (pemindai
  QR) disajikan dari `static/vendor`. Ubin peta dari OpenStreetMap (gratis).
  Bootstrap Icons dan Font Awesome masih dimuat dari CDN.

## Menjalankan secara lokal

```bash
cd petshop
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo          # opsional: data contoh
python manage.py runserver
```

Buka http://127.0.0.1:8000/. Tanpa variabel environment apa pun, aplikasi
berjalan dalam mode development dengan kunci rahasia khusus development.

**Kamera dan GPS** (foto bukti, scan QR, lokasi kurir) hanya diizinkan browser
di `https://` atau `http://localhost`. Untuk mencoba dari HP di jaringan yang
sama, pakai HTTPS (mis. reverse proxy dengan sertifikat) — lewat `http://IP-laptop`
browser akan menolak kamera/GPS.

### Data demo

ZIP rilis sudah berisi `petshop/db.sqlite3` yang terisi dan foto di
`petshop/media/`, jadi cukup `pip install -r requirements.txt` lalu
`python manage.py runserver`. Untuk membuat ulang dari nol:

```bash
python manage.py seed_demo --reset
```

Semua akun demo memakai kata sandi `demo12345` (ubah dengan `--password`).
Toko demo beralamat di Jl. Ery Suparjan No. 02, Samarinda; titik peta toko
perkiraan, geser di Pengaturan Toko bila kurang pas. Alamat pelanggan dan rute
kurir tersebar 1,5-9 km di sekitar toko.

**Akun berisi semua fitur.** Setiap peran punya aplikasinya sendiri, jadi ada
satu akun lengkap untuk staf dan satu untuk pelanggan:

| Akun | Peran | Mulai dari | Yang bisa dicoba |
| --- | --- | --- | --- |
| `demo_superadmin` | Super Admin | `/staff/admin/dashboard` | Semua menu admin dan kasir (ringkasan, laporan, produk, layanan, pesanan online, cek bukti transfer, packing, setoran COD, check-in hewan, komplain, kelola akun termasuk admin), `/admin/` |
| `demo_customer` | Pelanggan | `/dasbor/` | Pesanan sedang diantar (peta live), transfer belum dibayar, riwayat & ulasan, Mochi sedang dijemput kurir (peta live), Kopi waktunya grooming lagi + booking menunggu konfirmasi & terjadwal, riwayat tahap berfoto, komplain baru & selesai, notifikasi |

**Akun per fitur:**

| Akun | Peran | Mulai dari | Yang bisa dicoba |
| --- | --- | --- | --- |
| `demo_admin`, `demo_admin2` | Admin | `/staff/admin/dashboard` | Ringkasan, persetujuan staf (2 pendaftar menunggu), produk, layanan & tahapan, Pengaturan Toko |
| `demo_kasir` | Kasir | `/staff/admin/make_transaction/` | Shift kasir yang sedang buka, transaksi parkir "Bu Rina", scan kode barang, bayar campuran, retur menunggu; cek bukti transfer (ada yang menunggu), antrean packing & label, setoran COD, check-in & antrean hewan |
| `demo_kurir1` | Kurir | `/staff/courier/dashboard` | Rute aktif 3 alamat dengan peta, paket COD, uang COD yang belum disetor |
| `demo_kurir2` | Kurir (bisa bawa hewan) | `/staff/courier/dashboard` | Sedang menjemput hewan, jadi menu ambil paket terkunci (contoh aturan satu tugas); setoran menunggu kasir |
| `demo_kurir3` | Kurir (bisa bawa hewan, status istirahat) | `/staff/courier/dashboard` | Paket lunas siap diambil, jadwal antar-jemput hewan, riwayat setoran |
| `demo_groomer1`, `demo_groomer2` | Groomer | `/staff/groomer/dashboard` | Antrean hari ini, pekerjaan berjalan & siap diambil, kerjakan tahap dengan foto |
| `demo_belanja` | Pelanggan | `/pesanan-saya/` | Satu pesanan untuk tiap status: menunggu konfirmasi, transfer belum dibayar, bukti terkirim, bukti ditolak, dikemas, diantar (peta live), sampai, sudah diulas, dibatalkan |
| `demo_grooming` | Pelanggan | `/layanan/booking-saya/` | 3 hewan dan booking di tiap status: menunggu konfirmasi, terjadwal dengan antar-jemput, antre, dikerjakan, siap diambil, selesai (diulas & belum), batal |
| `demo_komplain` | Pelanggan | `/dasbor/` | Pesanan sampai (diulas & belum), komplain baru, diproses, dan selesai dengan balasan toko |
| `demo_calon_kurir`, `demo_calon_kurir2` | Pendaftar kurir | – | Belum bisa masuk sampai disetujui admin |

Isi data contoh (angka dari `seed_demo` bawaan):

| Data | Jumlah | Keterangan |
| --- | --- | --- |
| Produk | 44 | 5 kategori, harga beli/jual, tipe hewan, kondisi; ada yang habis, menipis, nonaktif, bekas |
| Mutasi stok | ±500 | Stok awal, restok, penjualan, pengembalian saat batal |
| Pelanggan | 34 | Nama, HP, alamat & titik peta di Samarinda, email `@example.com` |
| Order | ±190 | 90 hari, toko & online, tunai/COD & transfer, semua status, dengan nomor packing, resi, ongkir per km |
| Booking layanan | 54 | Selesai dengan foto tiap tahap, antre, dikerjakan, siap, menunggu konfirmasi, terjadwal, batal, tidak datang |
| Hewan pelanggan | 50 | Profil hewan dengan ras, umur, berat, catatan kesehatan |
| Transaksi kasir | ±25 | 4 hari terakhir: tunai/QRIS/campuran, diskon, 1 dibatalkan admin, 1 retur disetujui + 1 menunggu, 3 pembayaran grooming, 1 diantar kurir, 1 transaksi diparkir |
| Shift kasir | 4 | 3 sudah ditutup (1 selisih Rp 5.000 dengan catatan), 1 masih buka |
| Setoran COD | ±50 | Diterima (sebagian dengan selisih + catatan) dan menunggu |
| Lokasi kurir | beberapa titik | Jejak GPS untuk paket & hewan yang sedang diantar |
| Ulasan & komplain | beberapa | Rating pesanan/layanan dan 8 komplain (baru, diproses, selesai) |

Semua nama, nomor, alamat, dan email fiktif. Gambar QRIS di Pengaturan Toko
adalah **contoh bertuliskan "data demo"**, bukan QRIS sungguhan, dan rekening
bank demo bertanda "(contoh)"; ganti keduanya dengan milik toko sebelum dipakai.

Gambar data demo (semua file benar-benar ada di `media/`, tidak ada gambar rusak):

| Gambar | Sumber |
| --- | --- |
| Foto produk | Ilustrasi kemasan khusus per produk (`transaction/management/commands/demo_assets/products/`, dibuat ulang dengan `packshots.js`). Ganti dengan foto produk asli lewat Kelola Produk. |
| Foto profil staf & sebagian besar pelanggan, foto kurir | Ilustrasi DiceBear "notionists" berlisensi CC0 (`demo_assets/avatars/`) |
| Foto hewan, foto tahap grooming, check-in, jemput/antar | Potongan foto hewan di `static/` sesuai rasnya, dengan cap tahap & jam. Ras tanpa foto yang cocok (mis. kelinci, Pomeranian) dibiarkan tanpa foto. |
| Bukti transfer, foto serah terima paket | Tangkapan layar transfer umum (bertanda "Data contoh") dan foto paket dengan nama penerima & jam |

Database disalin tanpa folder `media/`? Jalankan `python manage.py seed_demo --media-only`
untuk memulihkan file demo yang hilang tanpa mengubah data lain.

Perintah ini menolak berjalan saat `DJANGO_DEBUG=0` kecuali diberi `--force`,
jadi jangan dipakai di server produksi.

Untuk akun Super Admin sungguhan:

```bash
python manage.py createsuperuser
python manage.py shell -c "from account.models import User; User.objects.filter(username='NAMA_USER').update(role='SUPERADMIN')"
```

## Perintah terjadwal

Jalankan lewat cron / Task Scheduler (mis. setiap 10 menit dan setiap pagi):

| Perintah | Fungsi |
| --- | --- |
| `python manage.py cancel_expired_orders` | Membatalkan pesanan transfer yang lewat batas bayar tanpa bukti, mengembalikan stok, memberi tahu pelanggan |
| `python manage.py send_grooming_reminders` | Mengirim notifikasi "waktunya grooming lagi" (sekali per layanan terakhir, interval di Pengaturan Toko) |
| `python manage.py audit_stock` | Memeriksa kecocokan stok dengan riwayat mutasi |

## Bahasa (ID/EN)

Tombol **ID/EN** ada di navbar pelanggan, sidebar staf, navbar kurir/groomer,
dan halaman masuk/daftar. Pilihan disimpan di cookie; tanpa pilihan situs selalu
tampil dalam Bahasa Indonesia. Terjemahan ada di
`petshop/locale/en/LC_MESSAGES/django.po`. Setelah mengubahnya jalankan:

```bash
python manage.py build_locale       # kompilasi .po -> .mo, tanpa GNU gettext
```

Label, placeholder, dan pesan error form ikut bahasa aktif lewat
`common/form_i18n.py`. Notifikasi, riwayat aktivitas, catatan mutasi stok, dan
pesan sukses/gagal yang disimpan dalam bahasa Indonesia diterjemahkan saat
ditampilkan (`common/stored_i18n.py`, filter template `|tr`): teksnya dicocokkan
dengan pola katalog seperti `Pesanan #%(order_pk)s dikonfirmasi`. Jumlah
memakai bentuk tunggal/jamak (`{% blocktranslate count %}`: "1 pet", "5 pets").
Katalog `locale/id` dipakai untuk menyeragamkan istilah Indonesia
("order" tampil sebagai "pesanan", "customer" sebagai "pelanggan").

Yang tetap berbahasa Indonesia: isi database yang ditulis pengguna (nama
produk/layanan/tahap, deskripsi, catatan, jawaban FAQ chatbot) dan pesan
WhatsApp ke admin.

## Konfigurasi (environment)

Daftar lengkap ada di [`petshop/.env.example`](petshop/.env.example). Aplikasi
membaca `os.environ` langsung; file itu hanya contoh dan tidak dibaca otomatis.

| Variabel | Keterangan |
| --- | --- |
| `DJANGO_DEBUG` | `1` development (bawaan), `0` produksi |
| `DJANGO_SECRET_KEY` | Wajib saat `DJANGO_DEBUG=0`; aplikasi menolak start tanpanya |
| `DJANGO_ALLOWED_HOSTS` | Domain dipisah koma |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Origin HTTPS dipisah koma |
| `DJANGO_DB_PATH` | Lokasi file SQLite (opsional) |
| `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_HSTS_SECONDS` | Pengaturan HTTPS produksi (opsional) |

Alamat & titik peta toko, nomor WhatsApp, rekening transfer, tarif ongkir dan
antar-jemput, jam buka, batas bayar, dan interval pengingat grooming diatur
admin di **Pengaturan Toko** (`/staff/admin/pengaturan-toko/`), bukan di kode.

## Tes

```bash
cd petshop
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

Tes juga memeriksa konvensi repo (tanpa `<style>`/`<script>` inline atau
`onclick=`, file statis yang dirujuk harus ada, variabel tema gelap) dan
kelengkapan terjemahan Inggris untuk semua teks template, kode Python, form,
notifikasi/riwayat yang disimpan, dan pesan error proses.

## Deploy (ringkas)

1. Set `DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
   `DJANGO_CSRF_TRUSTED_ORIGINS`.
2. `python manage.py migrate` dan `python manage.py collectstatic`.
3. Jalankan dengan server WSGI (mis. gunicorn `petshop.wsgi`) di belakang
   reverse proxy **HTTPS** (wajib untuk kamera & GPS).
4. Sajikan `staticfiles/` dan `media/` dari web server; Django tidak menyajikan
   media saat `DEBUG=0`. Folder `media/` berisi foto bukti transfer, bukti
   kirim, dan foto hewan — jangan dibuka publik tanpa perlu dan cadangkan rutin.
5. Pasang dua perintah terjadwal di atas.
6. Cadangkan file SQLite secara berkala.
7. `python manage.py check --deploy` untuk memeriksa pengaturan keamanan.

## Struktur folder

```
petshop/
  petshop/       settings, url utama
  account/       login, peran, pendaftaran & persetujuan staf, dasbor admin
  customer/      halaman toko, keranjang, checkout, dasbor & akun pelanggan
  product/       produk, kategori, stok & harga
  transaction/   order, pembayaran, bukti transfer, packing & label, seed_demo
  courier/       rute, lokasi GPS, serah terima, setoran COD
  service/       layanan, tahapan, booking, check-in & antrean, profil hewan, antar-jemput
  store/         pengaturan toko, notifikasi, log aktivitas, komplain, ulasan
  chatbot/       FAQ chatbot
  common/        helper bersama, middleware bahasa, perintah build_locale
  locale/        terjemahan Inggris
  templates/     halaman error & komponen bersama (kamera, tombol bahasa)
  static/        aset bersama & vendor
```

## Batasan yang diketahui

- Pembayaran sengaja tanpa payment gateway (gateway memotong biaya per
  transaksi): transfer manual dengan foto bukti yang dicek kasir terhadap
  mutasi rekening, atau COD yang disetor kurir ke kasir.
- QRIS memakai gambar QRIS statis dari bank (gratis). Kasir mengecek dana
  masuk secara manual lalu mencentang konfirmasi; tidak ada notifikasi otomatis.
- Struk dicetak lewat dialog cetak browser (printer thermal 58 mm diatur
  sebagai printer biasa); belum ada cetak langsung ESC/POS atau laci uang otomatis.
- Scan barcode batang lewat kamera hanya di browser yang mendukung
  BarcodeDetector (Chrome Android); di browser lain pakai scanner USB atau QR.
- Belum ada poin member.
- Tugas antar-jemput hewan tidak digabung ke optimasi rute paket; kurir
  mengerjakannya dari menu Hewan.
- Pelacakan realtime memakai pembaruan berkala (±10 detik), bukan WebSocket,
  dan hanya berjalan selama halaman kurir terbuka dengan GPS aktif.
- Notifikasi hanya di dalam aplikasi (lonceng), belum ada email/push.
- Lupa kata sandi ditangani admin (belum ada reset via email).
- SQLite cocok untuk satu toko dengan lalu lintas kecil–sedang.
