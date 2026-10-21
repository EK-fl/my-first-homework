/* ==========================================================================
   main.js — общая интерактивность сайта:
   мобильное меню, плавная прокрутка к каталогу, фильтрация и сортировка
   каталога, плавное появление блоков при прокрутке.
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function () {

  // --------------------------------------------------------------------------
  // 1. Мобильное меню (кнопка-гамбургер в шапке)
  // --------------------------------------------------------------------------
  const menuToggle = document.getElementById("menu-toggle");
  const mainNav = document.getElementById("main-nav");

  if (menuToggle && mainNav) {
    menuToggle.addEventListener("click", function () {
      const isOpen = mainNav.classList.toggle("is-open");
      menuToggle.setAttribute("aria-expanded", String(isOpen));
      menuToggle.setAttribute("aria-label", isOpen ? "Закрыть меню" : "Открыть меню");
    });

    // Клик по ссылке меню закрывает его
    mainNav.querySelectorAll(".nav-link").forEach(function (link) {
      link.addEventListener("click", function () {
        mainNav.classList.remove("is-open");
        menuToggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  // --------------------------------------------------------------------------
  // 2. Плавная прокрутка к каталогу по кнопке «Смотреть схемы»
  //    И учитываем липкую шапку: прокручиваем чуть выше якоря.
  // --------------------------------------------------------------------------
  const catalogSection = document.getElementById("catalog");

  document.querySelectorAll(".scroll-to-catalog").forEach(function (btn) {
    btn.addEventListener("click", function (event) {
      event.preventDefault();
      if (catalogSection) {
        const headerHeight = document.querySelector(".site-header")?.offsetHeight || 0;
        const top = catalogSection.getBoundingClientRect().top + window.scrollY - headerHeight - 10;
        window.scrollTo({ top: top, behavior: "smooth" });
      }
    });
  });

  // --------------------------------------------------------------------------
  // 3. Фильтрация и сортировка каталога
  //    Карточки уже отрендерены сервером; скрипт прячет/переставляет их.
  // --------------------------------------------------------------------------
  const grid = document.getElementById("catalog-grid");
  const searchInput = document.getElementById("filter-search");
  const categorySelect = document.getElementById("filter-category");
  const sortSelect = document.getElementById("sort-by");
  const emptyMessage = document.getElementById("catalog-empty");

  if (grid) {
    // «Родные» карточки: сохраняем порядок по умолчанию при сбросе сортировки
    const cards = Array.from(grid.querySelectorAll(".pattern-card"));
    const defaultOrder = cards.slice();

    /** Прячет карточки, не подходящие под поиск и категорию. */
    function applyFilters() {
      const query = (searchInput?.value || "").trim().toLowerCase();
      const category = categorySelect?.value || "";
      let visibleCount = 0;

      cards.forEach(function (card) {
        const title = card.dataset.title || "";
        // Категорию сравниваем без учёта регистра: в данных может быть
        // «Животные», а в фильтре значение приведено к нижнему регистру
        const cardCategory = (card.dataset.category || "").toLowerCase();
        const matchesQuery = !query || title.includes(query);
        const matchesCategory = !category || cardCategory === category;
        const visible = matchesQuery && matchesCategory;
        card.classList.toggle("is-hidden", !visible);
        if (visible) visibleCount++;
      });

      // Сообщение «ничего не найдено» — только когда есть карточки, но все скрыты
      if (emptyMessage) emptyMessage.hidden = !(visibleCount === 0 && cards.length > 0);
    }

    /** Переставляет карточки в выбранном порядке. */
    function applySort() {
      const mode = sortSelect?.value || "default";
      let sorted;

      switch (mode) {
        case "price-asc":
          sorted = cards.slice().sort(function (a, b) {
            return Number(a.dataset.price) - Number(b.dataset.price);
          });
          break;
        case "price-desc":
          sorted = cards.slice().sort(function (a, b) {
            return Number(b.dataset.price) - Number(a.dataset.price);
          });
          break;
        case "title-asc":
          sorted = cards.slice().sort(function (a, b) {
            return (a.dataset.title || "").localeCompare(b.dataset.title || "", "ru");
          });
          break;
        case "title-desc":
          sorted = cards.slice().sort(function (a, b) {
            return (b.dataset.title || "").localeCompare(a.dataset.title || "", "ru");
          });
          break;
        default:
          sorted = defaultOrder;
      }

      sorted.forEach(function (card) {
        grid.appendChild(card); // повторное добавление перемещает элемент
      });
    }

    if (searchInput) searchInput.addEventListener("input", applyFilters);
    if (categorySelect) categorySelect.addEventListener("change", applyFilters);
    if (sortSelect) sortSelect.addEventListener("change", applySort);
  }

  // --------------------------------------------------------------------------
  // 4. Плавное появление блоков при прокрутке (IntersectionObserver)
  //    Если браузер не поддерживает наблюдатель или выключена анимация —
  //    просто показываем всё сразу.
  // --------------------------------------------------------------------------
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const revealElements = document.querySelectorAll(".reveal");

  if (reducedMotion || !("IntersectionObserver" in window)) {
    revealElements.forEach(function (el) {
      el.classList.add("is-visible");
    });
  } else {
    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target); // появилось один раз — достаточно
        }
      });
    }, { threshold: 0.12 });

    revealElements.forEach(function (el) {
      observer.observe(el);
    });
  }
});
