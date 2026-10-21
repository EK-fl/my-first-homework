/* ==========================================================================
   gallery.js — модальное окно увеличенных изображений на странице схемы.

   Открывается по клику на основное изображение, дополнительные фото
   и фрагмент схемы 10×10. Закрывается по крестику, клавише Escape
   и клику вне изображения. Работает с клавиатуры (фокус возвращается
   на кнопку, с которой открыли окно).
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function () {

  const lightbox = document.getElementById("lightbox");
  const lightboxImg = document.getElementById("lightbox-img");
  if (!lightbox || !lightboxImg) return; // мы не на странице схемы

  // Элемент, который был в фокусе до открытия — вернём фокус при закрытии
  let lastFocused = null;

  /** Открывает модальное окно с указанным изображением. */
  function openLightbox(src, alt) {
    lastFocused = document.activeElement;
    lightboxImg.src = src;
    lightboxImg.alt = alt || "Увеличенное изображение";
    lightbox.hidden = false;
    document.body.style.overflow = "hidden"; // блокируем прокрутку страницы
    // Переводим фокус на кнопку закрытия для клавиатурной навигации
    lightbox.querySelector(".lightbox-close").focus();
  }

  /** Закрывает модальное окно и возвращает фокус. */
  function closeLightbox() {
    lightbox.hidden = true;
    lightboxImg.src = "";
    document.body.style.overflow = "";
    if (lastFocused && typeof lastFocused.focus === "function") {
      lastFocused.focus();
    }
  }

  // Все элементы с классом js-open-lightbox / js-open-preview открывают окно
  document.querySelectorAll(".js-open-lightbox, .js-open-preview").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const src = btn.dataset.full;
      if (src) openLightbox(src, btn.getAttribute("aria-label"));
    });
  });

  // Закрытие: крестик и клик по затемнённому фону
  lightbox.querySelectorAll("[data-close]").forEach(function (el) {
    el.addEventListener("click", closeLightbox);
  });

  // Закрытие: клавиша Escape
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !lightbox.hidden) {
      closeLightbox();
    }
  });
});
