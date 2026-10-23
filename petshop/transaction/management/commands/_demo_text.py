"""Teks contoh untuk seed_demo: deskripsi produk, pelanggan tambahan,
catatan pesanan, dan catatan booking. Semua nama, nomor, dan alamat fiktif."""

PRODUCT_DESCRIPTIONS = {
    "Royal Canin Kitten 400g": "Makanan kering untuk anak kucing usia 4–12 bulan. Butiran kecil mudah dikunyah, mendukung daya tahan tubuh dan pencernaan. Takaran: 40–60 g per hari dibagi 3–4 kali makan.",
    "Whiskas Pouch Tuna 85g": "Makanan basah rasa tuna dalam saus untuk kucing dewasa. Satu pouch untuk sekali makan; simpan sisa di kulkas maksimal 24 jam.",
    "Whiskas Junior Ocean Fish 1,1kg": "Makanan kering anak kucing 2–12 bulan rasa ikan laut, diperkaya DHA dan kalsium untuk tulang dan gigi.",
    "Me-O Tuna Dewasa 1,2kg": "Makanan kering kucing dewasa rasa tuna. Mengandung taurin untuk kesehatan mata dan omega 3 & 6 untuk bulu berkilau.",
    "Friskies Seafood 1kg": "Makanan kering kucing dewasa campuran rasa seafood. Kemasan zip-lock agar tetap renyah.",
    "Bolt Tuna Kaleng 400g": "Makanan basah kaleng rasa tuna untuk kucing. Bisa dicampur dengan makanan kering. Setelah dibuka, tutup rapat dan simpan di kulkas.",
    "Pedigree Adult Beef 1,5kg": "Makanan kering anjing dewasa rasa daging sapi dan sayuran. Takaran anjing 10 kg: sekitar 170 g per hari.",
    "Pro Plan Puppy 1kg": "Makanan kering anak anjing ras kecil–sedang, dengan kolostrum untuk daya tahan tubuh. Untuk usia 2–12 bulan.",
    "Makanan Ikan Hias 100g": "Pakan serpih (flakes) untuk ikan hias air tawar seperti guppy dan molly. Beri sedikit, habis dalam 2–3 menit, dua kali sehari.",
    "Pelet Ikan Koi 500g": "Pelet terapung untuk koi dan ikan kolam, membantu warna lebih cerah. Ukuran butir 3 mm.",
    "Biji-bijian Burung Kenari 500g": "Campuran biji milet, kenari seed, dan rapeseed untuk kenari dan burung kicau kecil.",
    "Pakan Kelinci Pelet Alfalfa 1kg": "Pelet alfalfa tinggi serat untuk kelinci. Berikan bersama rumput kering (hay) dan air bersih.",
    "Makanan Hamster Campur 250g": "Campuran biji, jagung, dan pelet untuk hamster, gerbil, dan tikus kecil. Satu sendok makan per hari.",
    "Mangkuk Makan Anti-Tumpah": "Mangkuk plastik dengan alas karet anti-selip, diameter 15 cm. Cocok untuk kucing dan anjing kecil; aman dicuci dengan sabun.",
    "Tempat Pasir Kucing + Sekop": "Bak pasir kucing ukuran 40 × 30 cm dengan bibir tinggi agar pasir tidak berceceran. Termasuk sekop.",
    "Pasir Kucing Gumpal 5L": "Pasir bentonite yang menggumpal saat basah, wangi lavender. Satu kantong cukup untuk sekitar 2 minggu untuk satu kucing.",
    "Kandang Travel Kecil": "Kandang bawa (pet carrier) untuk kucing atau anjing kecil hingga 5 kg. Pintu besi, ventilasi di kedua sisi, ukuran 48 × 32 × 30 cm.",
    "Kandang Hamster 2 Tingkat": "Kandang hamster dua lantai dengan tangga, roda putar, dan botol minum. Ukuran 47 × 30 × 38 cm.",
    "Sangkar Burung Kenari": "Sangkar besi bulat untuk kenari atau lovebird, diameter 30 cm, lengkap dengan tempat pakan dan minum.",
    "Akuarium Mini 30cm": "Akuarium kaca 30 × 20 × 20 cm (sekitar 12 liter) untuk ikan cupang atau guppy. Belum termasuk filter dan lampu.",
    "Kandang Lipat Kelinci": "Kandang kawat lipat untuk kelinci atau marmut, ukuran 80 × 50 × 55 cm, dengan alas plastik yang bisa ditarik untuk dibersihkan.",
    "Kandang Kucing Ukuran Sedang (Bekas)": "Kandang kucing bekas pakai, kondisi masih kokoh, sudah dibersihkan dan disemprot disinfektan. Ukuran 60 × 45 × 50 cm.",
    "Sisir Bulu Hewan": "Sisir besi dua sisi (rapat dan jarang) untuk merapikan dan mengangkat bulu rontok kucing dan anjing.",
    "Shampo Anti Kutu 250ml": "Shampo untuk kucing dan anjing yang membantu membasmi kutu dan menghilangkan bau. Diamkan busa 5 menit sebelum dibilas. Tidak untuk anak kucing di bawah 3 bulan.",
    "Tempat Tidur Hewan Empuk M": "Kasur bulat berbahan bulu lembut, diameter 50 cm, untuk kucing atau anjing kecil. Bisa dicuci mesin.",
    "Botol Minum Otomatis Hamster": "Botol minum gantung 125 ml dengan bola baja anti-bocor untuk hamster dan kelinci kecil.",
    "Kalung Kulit Anjing": "Kalung kulit sintetis dengan gesper besi dan ring untuk tali tuntun. Lingkar leher 30–40 cm.",
    "Harness Kucing Adjustable": "Harness model rompi untuk kucing, bisa diatur lingkar dada 28–40 cm, dilengkapi tali reflektif.",
    "Tali Tuntun 1,5m": "Tali tuntun nilon 1,5 m dengan pegangan empuk dan pengait putar, untuk anjing hingga 15 kg.",
    "Kalung Lonceng Kucing": "Kalung kain dengan lonceng kecil dan pengunci pengaman (breakaway) yang lepas bila tersangkut.",
    "Baju Anjing Motif Batik": "Baju anjing katun motif batik, ukuran S–M (lingkar dada 30–45 cm). Nyaman untuk cuaca panas.",
    "Hoodie Hewan Kecil": "Hoodie rajut untuk kucing atau anjing kecil, menjaga tubuh tetap hangat setelah mandi atau saat cuaca dingin.",
    "Vitamin Bulu Sehat 60 Tablet": "Suplemen biotin dan omega untuk mengurangi kerontokan dan membuat bulu berkilau. Satu tablet per hari untuk kucing atau anjing kecil.",
    "Obat Cacing Kucing 4 Tablet": "Obat cacing spektrum luas untuk kucing. Dosis: 1 tablet per 4 kg berat badan, ulangi setiap 3 bulan. Konsultasikan ke dokter hewan untuk kucing hamil.",
    "Obat Kutu Tetes Anjing": "Obat tetes kutu dan caplak untuk anjing 10–20 kg, diteteskan di tengkuk. Efektif sekitar 4 minggu.",
    "Salep Jamur Hewan 15g": "Salep untuk jamur kulit dan gatal pada kucing, anjing, dan kelinci. Oleskan tipis 2 kali sehari pada area yang bersih.",
    "Suplemen Kalsium Kelinci": "Tablet kalsium dan vitamin D untuk kelinci dan marmut, mendukung kesehatan tulang dan gigi.",
    "Mainan Kucing Felt": "Mainan berbahan felt berbentuk ikan dan tikus, ringan dan aman digigit. Isi 3 buah.",
    "Tongkat Bulu Kucing": "Tongkat pancing dengan bulu dan lonceng untuk bermain bersama kucing, panjang 45 cm.",
    "Tikus Mainan Catnip": "Tikus mainan berisi catnip kering yang membuat kucing aktif bermain. Isi 2 buah.",
    "Bola Karet Anjing": "Bola karet padat diameter 6 cm, memantul dan tahan gigitan, untuk anjing kecil–sedang.",
    "Tulang Karet Gigit": "Mainan gigit berbentuk tulang dari karet alami, membantu membersihkan gigi dan menyalurkan kebiasaan menggigit.",
    "Roda Putar Hamster": "Roda putar senyap diameter 18 cm dengan dudukan, untuk hamster syrian maupun dwarf.",
    "Ayunan Burung": "Ayunan kayu dengan manik-manik warna untuk sangkar kenari, lovebird, atau parkit.",
}

# (nama, nomor HP, alamat). Nomor 0813000000xx sengaja fiktif.
MORE_CUSTOMERS = [
    ("Eka Prasetya", "081300000017", "Jl. Ahmad Yani No. 41, Kel. Temindung Permai, Kec. Sungai Pinang"),
    ("Wulan Sari", "081300000018", "Jl. Perjuangan No. 8, RT 12, Kel. Sempaja Selatan, Kec. Samarinda Utara"),
    ("Doni Firmansyah", "081300000019", "Perumahan Bumi Sempaja Blok AB 3 No. 7, Kel. Sempaja Utara"),
    ("Sinta Maharani", "081300000020", "Jl. Ruhui Rahayu No. 2, Kel. Sempaja Selatan, Kec. Samarinda Utara"),
    ("Arif Budiman", "081300000021", "Jl. DI Panjaitan No. 19, Kel. Mugirejo, Kec. Sungai Pinang"),
    ("Novi Anggraeni", "081300000022", "Jl. Gatot Subroto No. 27, Kel. Bandara, Kec. Sungai Pinang"),
    ("Galih Pratama", "081300000023", "Jl. Kemakmuran No. 4, Kel. Sungai Pinang Dalam"),
    ("Ratna Dewi", "081300000024", "Jl. Bung Tomo No. 66, Kel. Sungai Keledang, Kec. Samarinda Seberang"),
    ("Irfan Hakim", "081300000025", "Jl. Rapak Indah No. 15, Kel. Lok Bahu, Kec. Sungai Kunjang"),
    ("Melati Kusuma", "081300000026", "Jl. Damanhuri No. 12, Kel. Mugirejo, Kec. Sungai Pinang"),
    ("Andi Saputra", "081300000027", "Jl. Sentosa No. 30, Kel. Sungai Pinang Dalam"),
    ("Citra Ayuningtyas", "081300000028", "Jl. Banggeris No. 5, RT 08, Kel. Bandara"),
    ("Hadi Wijaya", "081300000029", "Jl. Cipto Mangunkusumo No. 22, Kel. Harapan Baru, Kec. Loa Janan Ilir"),
    ("Laras Pertiwi", "081300000030", "Jl. Wahid Hasyim I No. 9, Kel. Sempaja Selatan"),
]

ORDER_NOTES = [
    "Tolong dibungkus rapi, untuk hadiah.",
    "Kirim sore setelah jam 4 ya.",
    "Rumah pagar hijau, sebelah warung.",
    "Kalau tidak ada orang, titip ke tetangga sebelah kanan.",
    "Mohon cek tanggal kedaluwarsa sebelum dikirim.",
    "Telepon dulu sebelum sampai.",
]

BOOKING_NOTES = [
    "Kucingnya agak penakut, mohon pelan-pelan.",
    "Bulu di bagian ekor kusut.",
    "Ada sedikit ketombe di punggung.",
    "Tolong kukunya dipotong pendek.",
    "Anjingnya suka menggigit saat dikeringkan.",
    "",
    "",
]

GROOMER_NOTES = [
    "Bersih, wangi, kuku sudah dipotong.",
    "Ditemukan sedikit kutu, sudah ditangani dengan shampo anti kutu.",
    "Bulu kusut di ekor sudah dirapikan.",
    "Telinga dibersihkan, tidak ada tanda infeksi.",
    "Hewan tenang selama perawatan.",
]

PET_NAMES_MORE = [
    ("Milo", "KUCING"), ("Coco", "ANJING"), ("Simba", "KUCING"),
    ("Bella", "ANJING"), ("Kiki", "KELINCI"), ("Tom", "KUCING"),
]
