// Galeri nilai: tombol kiri/kanan menggeser satu kartu (scroll biasa dan keyboard tetap bisa).
(function () {
    var rail = document.getElementById("values-rail");
    var prev = document.getElementById("rail-prev");
    var next = document.getElementById("rail-next");
    if (!rail || !prev || !next) return;
    var calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    function step() {
        var card = rail.querySelector(".sx-vp");
        return card ? card.getBoundingClientRect().width + 20 : 300;
    }
    function update() {
        prev.disabled = rail.scrollLeft <= 2;
        next.disabled = rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 2;
    }
    prev.addEventListener("click", function () { rail.scrollBy({ left: -step(), behavior: calm ? "auto" : "smooth" }); });
    next.addEventListener("click", function () { rail.scrollBy({ left: step(), behavior: calm ? "auto" : "smooth" }); });
    rail.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    update();
})();
