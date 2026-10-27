/*
 * Terjemahan teks yang dibuat JavaScript (status kamera, GPS, peta, keranjang…).
 * Bahasa mengikuti <html lang>, yang diatur tombol ID/EN. Teks sumber = Bahasa Indonesia;
 * teks yang tidak ada di kamus tampil apa adanya.
 *
 *   window.petT("Jarak kurir ke {dest} ±{km} km", { dest: "...", km: 2.5 })
 */
(function () {
  "use strict";

  var EN = {
    "Sinyal GPS kurir terputus · ": "Courier GPS signal lost · ",
    "Diperbarui ": "Updated ",
    "Jarak kurir ke {dest} ±{km} km": "Courier is ±{km} km from {dest}",
    "alamat Anda": "your address",
    "rumah Anda": "your home",
    "toko": "the store",
    "perkiraan tiba ±{n} menit": "arriving in about {n} min",
    "Anda tujuan berikutnya": "You are the next stop",
    "{n} pengantaran lagi sebelum Anda": "{n} more deliveries before you",
    "Menunggu lokasi kurir": "Waiting for the courier location",
    "Menunggu kurir mengambil paket": "Waiting for a courier to pick up the parcel",
    "Gagal memuat lokasi, mencoba lagi…": "Could not load the location, retrying…",
    "baru saja": "just now",
    "{n} detik lalu": "{n} seconds ago",
    "{n} menit lalu": "{n} minutes ago",
    "Posisi kurir": "Courier position",
    "Tujuan": "Destination",
    "Toko": "Store",
    "Ambil foto dulu sebelum mengirim.": "Take a photo before sending.",
    "Browser ini tidak bisa membuka kamera langsung.": "This browser cannot open the camera directly.",
    "Situs belum memakai HTTPS, jadi kamera bawaan HP yang dibuka.": "This site is not on HTTPS yet, so the phone's camera app is opened.",
    "Browser ini tidak bisa membuka kamera langsung, jadi kamera bawaan HP yang dibuka.": "This browser cannot open the camera directly, so the phone's camera app is opened.",
    "Membuka kamera…": "Opening camera…",
    "Arahkan kamera lalu tekan Ambil foto.": "Point the camera, then press Take Photo.",
    "Izin kamera ditolak. Izinkan kamera di pengaturan browser.": "Camera permission denied. Allow the camera in the browser settings.",
    "Kamera tidak bisa dibuka.": "The camera could not be opened.",
    "Browser tidak mendukung foto langsung.": "The browser does not support taking photos directly.",
    "Foto siap dikirim.": "Photo ready to send.",
    "Kamera tidak tersedia di browser ini. Ketik kodenya secara manual.": "The camera is not available in this browser. Type the code manually.",
    "Tutup kamera": "Close camera",
    "Arahkan kamera ke QR…": "Point the camera at the QR…",
    "Kamera tidak bisa dibuka (izin ditolak / bukan HTTPS). Ketik kodenya secara manual.": "The camera could not be opened (permission denied / not HTTPS). Type the code manually.",
    "Scan QR": "Scan QR",
    "Izin lokasi ditolak. Buka pengaturan browser > Izin situs > Lokasi, pilih Izinkan, lalu tekan Coba lagi.": "Location permission denied. Open browser settings > Site permissions > Location, choose Allow, then press Try again.",
    "Browser ini tidak mendukung GPS. Gunakan Chrome atau Safari terbaru.": "This browser does not support GPS. Use the latest Chrome or Safari.",
    "Mencari posisi GPS…": "Finding GPS position…",
    "GPS aktif": "GPS on",
    "GPS mati": "GPS off",
    "GPS belum mendapat posisi. Nyalakan Lokasi/GPS di HP lalu tunggu beberapa detik.": "GPS has no position yet. Turn on Location/GPS on the phone and wait a few seconds.",
    "GPS hanya bisa dipakai lewat HTTPS. Buka situs dengan alamat https://.": "GPS only works over HTTPS. Open the site with an https:// address.",
    "Sinyal GPS hilang lebih dari {n} detik. Pastikan Lokasi HP menyala.": "GPS signal lost for more than {n} seconds. Make sure the phone's Location is on.",
    "Geser untuk memindahkan": "Drag to move",
    "Lokasi tidak bisa dibaca. Izinkan akses lokasi di browser, atau klik titik di peta.": "Location could not be read. Allow location access in the browser, or click a point on the map.",
    "Sisa stok {n}": "{n} left in stock",
    "Kurangi jumlah": "Decrease quantity",
    "Tambah jumlah": "Increase quantity",
    "Hapus {name} dari keranjang": "Remove {name} from cart",
    "Tidak bisa memeriksa harga terbaru (koneksi bermasalah). Harga akan dicek ulang saat checkout.": "Could not check the latest prices (connection problem). Prices will be re-checked at checkout.",
    "Pilih titik di peta": "Choose a point on the map",
    "Titik tersimpan. Jarak dari toko ±{km} km.": "Point saved. Distance from the store ±{km} km.",
    "Di luar jangkauan": "Out of range",
    "Gagal menghitung ongkir": "Could not calculate shipping",
    "Alamat pengiriman wajib diisi.": "The shipping address is required.",
    "Titik pengiriman di luar jangkauan antar toko.": "The delivery point is outside the store's delivery range.",
    "Tandai titik lokasi pengiriman di peta dulu.": "Mark the delivery point on the map first.",
    "Buat pesanan sekarang?": "Place the order now?",
    "Server sedang bermasalah. Coba lagi beberapa saat lagi.": "The server is having problems. Try again in a moment.",
    "Sesi login Anda berakhir. Muat ulang halaman lalu masuk kembali.": "Your login session has ended. Reload the page and sign in again.",
    "Pesanan gagal dibuat.": "The order could not be created.",
    "Koneksi bermasalah, coba lagi.": "Connection problem, please try again.",
    "Nomor telepon wajib diisi.": "The phone number is required.",
    "Nomor telepon tidak valid. Contoh: 081234567890": "Invalid phone number. Example: 081234567890",
    "{label} wajib diisi.": "{label} is required.",
    "Nama lengkap": "Full name",
    "Alamat": "Address",
    "Periksa pesanan Anda:": "Review your order:",
    "Nama": "Name",
    "Telepon": "Phone",
    "Pembayaran": "Payment",
    "Kirim pesanan sekarang?": "Send the order now?",
    "Keranjang belanja Anda kosong!": "Your shopping cart is empty!",
    "Ditambahkan ke favorit": "Added to favourites",
    "Dihapus dari favorit": "Removed from favourites",
    "Asisten sedang mengetik": "The assistant is typing",
    "Tutup chat bantuan": "Close help chat",
    "Buka chat bantuan": "Open help chat",
    "Mencocokkan…": "Matching…",
    "Gagal mengecek, periksa sinyal lalu coba lagi.": "Check failed, check your signal and try again.",
    "QR terbaca.": "QR read.",
    "ongkir": "shipping",
    "Ongkir otomatis {n}": "Auto shipping {n}",
    "Gagal menyimpan. Coba lagi.": "Could not save. Please try again.",
    "Isi nama, nomor WhatsApp, dan alamat.": "Fill in the name, WhatsApp number, and address.",
    "Non-tunai lebih": "Non-cash over by",
    "Kurang": "Short",
    "Kembalian": "Change"
  };

  window.petLang = (document.documentElement.getAttribute("lang") || "id").slice(0, 2);
  window.petT = function (text, vars) {
    var out = (window.petLang === "en" && EN[text]) || text;
    if (vars) {
      Object.keys(vars).forEach(function (key) {
        out = out.split("{" + key + "}").join(vars[key]);
      });
    }
    return out;
  };
})();
