"""Teks contoh untuk seed_demo: deskripsi produk, pelanggan tambahan,
catatan pesanan, dan catatan booking. Semua nama, nomor, dan alamat fiktif."""

PRODUCT_DESCRIPTIONS = {
    "Bolt Tuna Mother & Kitten Kaleng 400g": "Makanan basah kaleng untuk induk kucing yang menyusui dan anak kucing mulai usia 1 bulan. Tekstur lembut mudah dikunyah. Setelah dibuka, tutup rapat dan simpan di kulkas maksimal 2 hari.",
    "Bolt Salmon Kaleng 400g": "Makanan basah kaleng rasa salmon untuk kucing dewasa. Bisa diberikan langsung atau dicampur makanan kering. Simpan sisa di kulkas, habiskan dalam 2 hari.",
    "Bolt Tuna Kaleng 400g": "Makanan basah kaleng rasa tuna untuk kucing dewasa, formula lengkap & seimbang. Setelah dibuka, tutup rapat dan simpan di kulkas.",
    "Bolt Tuna & Sardines Kaleng 400g": "Makanan basah kaleng perpaduan tuna dan sarden untuk kucing dewasa. Kaya protein ikan untuk bulu berkilau.",
    "Bolt Mixed Fish Platter Kaleng 400g": "Makanan basah kaleng campuran aneka ikan untuk kucing dewasa yang suka variasi rasa.",
    "Bolt Plus Tuna & Chicken 5kg": "Makanan kering kucing dewasa rasa tuna dan ayam dengan butiran bentuk spinner. Kemasan 5 kg hemat untuk rumah dengan banyak kucing.",
    "Bolt Tuna Kibble Ikan 20kg": "Makanan kering kucing dewasa rasa tuna, butiran bentuk ikan. Karung 20 kg isi 25 × 800 g, praktis untuk peternak atau penampungan kucing.",
    "Bolt Dog Puppy 800g": "Makanan kering anak anjing usia 2–12 bulan. Butiran kecil, mendukung pertumbuhan tulang dan daya tahan tubuh.",
    "Bolt Dog Small Breed Adult 20kg": "Makanan kering anjing dewasa ras kecil (pom, shih tzu, poodle). Karung 20 kg isi 25 × 800 g.",
    "Bolt Dog Lamb Kibble Bulat 20kg": "Makanan kering anjing dewasa rasa domba, butiran bulat. Karung 20 kg isi 20 × 1 kg.",
    "Bolt Dog Beef Kibble Segitiga 20kg": "Makanan kering anjing dewasa rasa daging sapi, butiran segitiga. Karung 20 kg isi 20 × 1 kg.",
    "Takari Koki Sinking 100g": "Pakan tenggelam untuk ikan koki (mas koki), butiran halus mudah dicerna. Beri sedikit, habis dalam 2–3 menit, dua kali sehari.",
    "Takari Mix 100g": "Pakan terapung campuran untuk ikan hias kolam dan akuarium. Membantu warna dan pertumbuhan.",
    "Takari Red 100g": "Pakan terapung penambah warna merah untuk koi dan ikan hias.",
    "Takari Green 100g": "Pakan terapung dengan spirulina untuk menjaga kesehatan pencernaan ikan hias.",
    "Pakan Ikan Koi PK 2mm 10kg": "Pelet terapung butir 2 mm untuk koi kecil dan ikan kolam. Karung 10 kg.",
    "Pakan Ikan Koi PK 5mm 10kg": "Pelet terapung butir 5 mm untuk koi dewasa. Karung 10 kg.",
    "Pakan Ikan Koi Spesial 10kg": "Pelet koi formula spesial untuk pertumbuhan badan. Karung 10 kg.",
    "Pakan Koi Super Red 10kg": "Pelet koi penambah warna merah (PK-SR). Karung 10 kg.",
    "Tory Daily Pakan Burung Dewasa 100g": "Pakan harian burung kicau dewasa seperti murai dan kacer. Nutrisi seimbang untuk stamina dan bulu.",
    "Tory Junior Pakan Anakan Burung 100g": "Pakan lunak untuk anakan burung, mudah dilolohkan. Diseduh air hangat sebelum diberikan.",
    "Tory Fighter Pakan Burung Kontes 100g": "Pakan burung kontes dengan protein tinggi untuk menjaga birahi dan performa saat lomba.",
    "C.P. Singing Bird Food": "Pakan pelet untuk burung kicau kecil seperti pleci, kenari, dan ciblek.",
    "Classic Singing Bird Food Seaweed 400g": "Pakan burung kicau dengan rumput laut dan ekstrak herbal. Membantu suara lebih merdu dan kotoran padat.",
    "Classic Singing Bird Food Anti Stress 400g": "Pakan burung kicau dengan ramuan anti stres, cocok untuk burung baru dibeli atau setelah perjalanan.",
    "Nice Makanan Kelinci Dewasa 1kg": "Pelet kelinci dewasa dengan serat tinggi. Berikan bersama rumput kering (hay) dan air bersih.",
    "Hamutaro Rainbow Premium Hamster Food": "Campuran biji, buah kering, dan pelet warna-warni untuk hamster. Satu sendok makan per hari.",
    "BentoCat Premium Clumping Litter 10L": "Pasir bentonite premium yang cepat menggumpal dan menyerap bau. Kemasan 10 liter cukup sekitar 3 minggu untuk satu kucing.",
    "Kandang Kucing Sweet Cage Size L (Bekas)": "Kandang kucing besi ukuran L dengan roda, bekas pakai pelanggan. Kondisi masih kokoh, sudah dibersihkan dan disemprot disinfektan.",
    "Baju Kucing Batik Nusantara": "Kemeja batik untuk kucing, bahan katun adem. Tersedia ukuran S–L; ukur lingkar dada sebelum membeli.",
    "Tali Tuntun Anjing Tambang Thomas": "Tali tuntun anjing dari tali tambang katun daur ulang, panjang 1,5 m, dengan pengait logam kuat.",
    "Diarril Kelinci Kapsul": "Obat diare untuk kelinci. Isi 10 kapsul. Ikuti dosis pada kemasan; bila diare lebih dari 2 hari, bawa ke dokter hewan.",
    "Ketwol Drops 15ml": "Obat tetes untuk membantu meredakan gejala flu dan pilek pada kucing. Botol 15 ml dengan pipet.",
    "Pussycap Kapsul Vitamin Kucing": "Vitamin kapsul untuk menjaga daya tahan tubuh dan nafsu makan kucing dewasa. Isi 10 kapsul.",
    "Rabbittoxy Stop Pilek Kelinci": "Obat pilek untuk kelinci. Isi 10 kapsul. Pisahkan kelinci yang sakit dari kelinci lain.",
    "Terafit 10 Kapsul Obat Burung": "Obat untuk membantu mengatasi infeksi pada burung kesayangan. Isi 10 kapsul.",
    "Whiscat Shampoo Kucing": "Shampo pengharum dan pembersih bulu kucing. Bilas sampai bersih dan keringkan dengan handuk.",
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
