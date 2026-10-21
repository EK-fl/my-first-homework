/* ==========================================================================
   carousel.js — галерея готовых работ.

   На компьютере работы показываются сеткой (несколько в ряд).
   На телефоне — «карусель»: ряды, которые можно листать свайпом.

   Принцип простой: на широком экране изображения выстраиваются в сетку,
   на узком — в горизонтальную ленту с прокруткой. Никаких тяжёлых
   библиотек: только CSS scroll-snap и небольшая подсказка о свайпе.

   Скрипт также следит за кнопками-точками (если они есть в разметке).
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function () {

  document.querySelectorAll("[data-carousel]").forEach(function (track) {
    const dotsHolder = document.querySelector(
      "[data-carousel-dots='" + track.dataset.carousel + "']"
    );

    // Свайп работает средствами самого браузера (scroll-snap),
    // поэтому JS нужен только для точек и подсказки.
    if (!dotsHolder) return;

    const slides = Array.from(track.children);
    if (slides.length === 0) return;

    slides.forEach(function (slide, index) {
      const dot = document.createElement("button");
      dot.type = "button";
      dot.className = "carousel-dot";
      dot.setAttribute("aria-label", "Работа " + (index + 1));
      dot.addEventListener("click", function () {
        // Прокручиваем к выбранной работе
        track.scrollTo({ left: slide.offsetLeft - track.offsetLeft, behavior: "smooth" });
      });
      dotsHolder.appendChild(dot);
    });

    const dots = Array.from(dotsHolder.children);

    /** Подсвечивает точку той работы, которая сейчас видна. */
    function updateDots() {
      const center = track.scrollLeft + track.clientWidth / 2;
      let closest = 0;
      let closestDistance = Infinity;
      slides.forEach(function (slide, index) {
        const slideCenter = slide.offsetLeft - track.offsetLeft + slide.clientWidth / 2;
        const distance = Math.abs(slideCenter - center);
        if (distance < closestDistance) {
          closestDistance = distance;
          closest = index;
        }
      });
      dots.forEach(function (dot, index) {
        dot.classList.toggle("is-active", index === closest);
      });
    }

    track.addEventListener("scroll", updateDots, { passive: true });
    updateDots();
  });
});
