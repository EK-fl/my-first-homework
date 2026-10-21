/* ==========================================================================
   admin.js — небольшая интерактивность админ-панели.

   Здесь всего четыре вещи:

   1. Мобильное меню (кнопка-гамбургер).
   2. Подтверждение перед удалением.
   3. Автоматический адрес страницы (slug) из названия схемы.
   4. Изменение порядка фотографий в галерее без перезагрузки страницы.

   Панель работает и без этого файла: все действия доступны и через
   обычные кнопки. JavaScript только делает работу удобнее.
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function () {

  // ------------------------------------------------------------------------
  // 1. Мобильное меню
  // ------------------------------------------------------------------------
  const menuToggle = document.getElementById("admin-menu-toggle");
  const nav = document.getElementById("admin-nav");

  if (menuToggle && nav) {
    menuToggle.addEventListener("click", function () {
      const isOpen = nav.classList.toggle("is-open");
      menuToggle.setAttribute("aria-expanded", String(isOpen));
      menuToggle.setAttribute("aria-label", isOpen ? "Закрыть меню" : "Открыть меню");
    });
  }

  // ------------------------------------------------------------------------
  // 2. Подтверждение перед удалением
  //    Удаление всегда мягкое (с возможностью восстановления), но
  //    лишний вопрос «вы уверены?» уберегает от случайного нажатия.
  // ------------------------------------------------------------------------
  document.querySelectorAll(".js-confirm").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      const message = form.dataset.confirm || "Вы уверены?";
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  // ------------------------------------------------------------------------
  // 3. Адрес страницы из названия
  //    Транслитерация русских букв в латиницу — то же правило,
  //    что и на сервере (функция slug_from_name в database.py).
  // ------------------------------------------------------------------------
  const TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "«": "", "»": "", "\"": "", " ": "-", "—": "-", "–": "-",
  };

  /** Делает из названия адрес: «Ехидная лисица» → «ehidnaya-lisitsa». */
  function makeSlug(text) {
    let result = "";
    for (const char of String(text || "").toLowerCase()) {
      if (TRANSLIT[char] !== undefined) {
        result += TRANSLIT[char];
      } else if (/[a-z0-9]/.test(char)) {
        result += char;
      } else {
        result += "-";
      }
    }
    // Убираем повторяющиеся дефисы и дефисы по краям
    result = result.replace(/-+/g, "-").replace(/^-|-$/g, "");
    return result.slice(0, 180);
  }

  const slugField = document.getElementById("slug");
  const titleField = document.getElementById("title");
  const slugButton = document.getElementById("make-slug");

  if (slugButton && slugField && titleField) {
    slugButton.addEventListener("click", function () {
      const slug = makeSlug(titleField.value);
      if (!slug) {
        window.alert("Сначала введите название схемы — из него получится адрес.");
        return;
      }
      slugField.value = slug;
      slugField.focus();
    });
  }

  // Если адрес ещё пустой, а название уже введено — заполняем автоматически
  if (slugField && titleField && !slugField.value) {
    titleField.addEventListener("blur", function () {
      if (!slugField.value && titleField.value.trim()) {
        slugField.value = makeSlug(titleField.value);
      }
    });
  }

  // ------------------------------------------------------------------------
  // 4. Порядок фотографий в галерее
  //    Кнопки «вверх» и «вниз» переставляют карточки местами.
  //    Скрытые поля внутри карточек хранят пути — сервер читает их
  //    по порядку следования и сохраняет галерею в нужном порядке.
  // ------------------------------------------------------------------------
  const galleryList = document.getElementById("gallery-list");

  if (galleryList) {
    function refreshButtons() {
      const items = Array.from(galleryList.querySelectorAll(".admin-gallery-item"));
      items.forEach(function (item, index) {
        // Удалённые фотографии не должны мешать порядку
        const isRemoved = item.classList.contains("is-removed");
        item.querySelector(".js-move-up").disabled = isRemoved || index === 0;
        item.querySelector(".js-move-down").disabled = isRemoved || index === items.length - 1;
      });
    }

    galleryList.addEventListener("click", function (event) {
      const upButton = event.target.closest(".js-move-up");
      const downButton = event.target.closest(".js-move-down");
      const removeButton = event.target.closest(".js-remove-image");

      if (upButton) {
        const item = upButton.closest(".admin-gallery-item");
        const previous = item.previousElementSibling;
        if (previous) galleryList.insertBefore(item, previous);
      } else if (downButton) {
        const item = downButton.closest(".admin-gallery-item");
        const next = item.nextElementSibling;
        if (next) galleryList.insertBefore(next, item);
      } else if (removeButton) {
        const item = removeButton.closest(".admin-gallery-item");
        const title = item.querySelector("img")?.alt || "эту фотографию";
        if (window.confirm("Убрать " + title.toLowerCase() + " из карточки?")) {
          // Прячем карточку: её скрытое поле больше не отправится? Нет —
          // скрытые поля уходят всегда, поэтому отключаем и поле тоже.
          const hiddenField = item.querySelector('input[type="hidden"]');
          if (hiddenField) hiddenField.disabled = true;
          item.classList.add("is-removed");
        }
      }

      refreshButtons();
    });

    refreshButtons();
  }

});
