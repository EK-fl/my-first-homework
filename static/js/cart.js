/* ==========================================================================
   cart.js — управление корзиной (localStorage)

   Корзина хранит ТОЛЬКО идентификаторы схем (их числа id).
   Названия, цены и картинки скрипт берёт из блока <script id="catalog-data">,
   который Flask вставляет в каждую страницу. Поэтому, если цена изменится,
   корзина сразу покажет новую цену.

   Доступные функции (можно вызывать из консоли браузера для проверки):
     addToCart(id)        — добавить схему
     removeFromCart(id)   — удалить схему
     getCart()            — список id в корзине
     getCartCount()       — количество схем
     getCartTotal()       — итоговая сумма (число)
     updateCartBadge()    — обновить счётчик в шапке
     renderCart()         — перерисовать страницу корзины (если она открыта)
   ========================================================================== */

// Ключ, под которым корзина лежит в localStorage браузера
const CART_KEY = "echidnye_krestiki_cart";

// --------------------------------------------------------------------------
// Каталог схем: читаем JSON, вставленный сервером в <script id="catalog-data">
// --------------------------------------------------------------------------
function loadCatalog() {
  const el = document.getElementById("catalog-data");
  if (!el) return [];
  try {
    return JSON.parse(el.textContent);
  } catch (e) {
    // Повреждённые данные каталога не должны ломать страницу
    console.warn("Не удалось разобрать данные каталога:", e);
    return [];
  }
}

const EK_CATALOG = loadCatalog();

// --------------------------------------------------------------------------
// Работа с localStorage. Может быть недоступна (например, в приватном
// режиме некоторых браузеров) — тогда корзина живёт только до перезагрузки,
// но сайт продолжает работать.
// --------------------------------------------------------------------------
function storageAvailable() {
  try {
    const test = "__ek_test__";
    localStorage.setItem(test, test);
    localStorage.removeItem(test);
    return true;
  } catch (e) {
    return false;
  }
}

const HAS_STORAGE = storageAvailable();

/**
 * Читает список id из хранилища. Если данные повреждены — возвращает пустой
 * список.
 */
function getCart() {
  if (!HAS_STORAGE) return [];
  try {
    const raw = localStorage.getItem(CART_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) throw new Error("ожидался массив");
    // Оставляем только положительные целые числа — чужие значения отбрасываем
    return parsed.filter((id) => Number.isInteger(id) && id > 0);
  } catch (e) {
    // Данные повреждены: сбрасываем, чтобы браузер не ругался каждый раз
    console.warn("Корзина была повреждена и сброшена:", e);
    saveCart([]);
    return [];
  }
}

/** Сохраняет список id в хранилище. */
function saveCart(ids) {
  if (!HAS_STORAGE) return;
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(ids));
  } catch (e) {
    console.warn("Не удалось сохранить корзину:", e);
  }
}

// --------------------------------------------------------------------------
// Основные операции
// --------------------------------------------------------------------------

/**
 * Добавляет схему в корзину. Повторное нажатие не создаёт дубликат —
 * цифровые товары покупаются только один раз.
 * Возвращает true, если товар действительно был добавлен.
 */
function addToCart(id) {
  id = Number(id);
  const catalogIds = EK_CATALOG.map((p) => p.id);
  if (!catalogIds.includes(id)) {
    console.warn("Схема с id", id, "не найдена в каталоге.");
    return false;
  }
  const cart = getCart();
  if (cart.includes(id)) return false; // уже в корзине — дубликат не нужен
  cart.push(id);
  saveCart(cart);
  updateCartBadge();
  renderCart();
  return true;
}

/** Удаляет схему из корзины по id. */
function removeFromCart(id) {
  id = Number(id);
  const cart = getCart().filter((x) => x !== id);
  saveCart(cart);
  updateCartBadge();
  renderCart();
}

/** Количество схем в корзине. */
function getCartCount() {
  return getCart().length;
}

/**
 * Красиво показывает цену: 350 → «350», 349.5 → «349.50».
 * Убирает лишние нули после запятой, чтобы не было «350.0».
 */
function formatPrice(value) {
  const number = Number(value) || 0;
  if (Number.isInteger(number)) return String(number);
  return number.toFixed(2);
}

/**
 * Итоговая сумма корзины (число, в рублях).
 * Считается по актуальным ценам из каталога — суммы из браузера не сохраняются.
 */
function getCartTotal() {
  const ids = getCart();
  return EK_CATALOG
    .filter((p) => ids.includes(p.id))
    .reduce((sum, p) => sum + (Number(p.price) || 0), 0);
}

// --------------------------------------------------------------------------
// Обновление интерфейса
// --------------------------------------------------------------------------

/** Обновляет счётчик товаров в шапке и коротко «подпрыгивает» при росте. */
function updateCartBadge() {
  const badge = document.getElementById("cart-badge");
  if (!badge) return;
  const count = getCartCount();
  badge.textContent = String(count);
  badge.hidden = count === 0;
  // Анимация только при изменении числа
  if (count > 0) {
    badge.classList.remove("bump");
    // Перезапуск анимации: убираем класс, ждём кадр, добавляем снова
    void badge.offsetWidth;
    badge.classList.add("bump");
  }
}

/**
 * Перерисовывает страницу корзины, если её элементы есть на странице.
 * Вызывается автоматически при добавлении/удалении товара.
 */
function renderCart() {
  const itemsBox = document.getElementById("cart-items");
  if (!itemsBox) return; // мы не на странице корзины

  const emptyBox = document.getElementById("cart-empty");
  const summaryBox = document.getElementById("cart-summary");
  const countEl = document.getElementById("cart-count");
  const totalEl = document.getElementById("cart-total");

  const ids = getCart();
  const items = EK_CATALOG.filter((p) => ids.includes(p.id));

  // Если какая-то схема пропала из каталога (удалена или отключена),
  // убираем её id из корзины, чтобы счётчик не врал
  const validIds = items.map((p) => p.id);
  if (validIds.length !== ids.length) {
    saveCart(validIds);
    updateCartBadge();
  }

  // Очищаем список (безопаснее, чем innerHTML с данными)
  itemsBox.textContent = "";

  items.forEach((p) => {
    const card = document.createElement("article");
    card.className = "cart-item";

    // Миниатюра
    const imgWrap = document.createElement("div");
    imgWrap.className = "cart-item-image";
    const img = document.createElement("img");
    img.src = p.image_url;
    img.alt = "Схема «" + p.title + "»";
    img.loading = "lazy";
    // Если картинка не загрузилась — прячем её, остаётся аккуратная подложка
    img.addEventListener("error", function () {
      img.style.display = "none";
    });
    imgWrap.appendChild(img);

    // Название (ссылка на страницу схемы) и цена
    const info = document.createElement("div");
    const title = document.createElement("p");
    title.className = "cart-item-title";
    const link = document.createElement("a");
    link.href = p.url;
    link.textContent = p.title;
    title.appendChild(link);

    const price = document.createElement("p");
    price.className = "cart-item-price";
    price.textContent = formatPrice(p.price) + " ₽";

    info.appendChild(title);
    info.appendChild(price);

    // Кнопка удаления
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "cart-item-remove";
    removeBtn.setAttribute("aria-label", "Удалить «" + p.title + "» из корзины");
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", function () {
      removeFromCart(p.id);
      showToast("Схема удалена из корзины");
    });

    card.appendChild(imgWrap);
    card.appendChild(info);
    card.appendChild(removeBtn);
    itemsBox.appendChild(card);
  });

  const isEmpty = items.length === 0;
  if (emptyBox) emptyBox.hidden = !isEmpty;
  if (summaryBox) summaryBox.hidden = isEmpty;
  if (countEl) countEl.textContent = String(items.length);
  if (totalEl) totalEl.textContent = formatPrice(getCartTotal()) + " ₽";
}

// --------------------------------------------------------------------------
// Уведомление «Добавлено в корзину»
// --------------------------------------------------------------------------
let toastTimer = null;

function showToast(message) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  // Показываем 2.5 секунды, затем прячем
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2500);
}

// --------------------------------------------------------------------------
// Инициализация: обработчики всех кнопок «Добавить в корзину»
// --------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", function () {
  updateCartBadge();
  renderCart();

  // Кнопки добавления есть и в каталоге, и на странице схемы
  document.querySelectorAll(".add-to-cart").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const id = btn.dataset.id;
      const added = addToCart(id);

      // Всегда показываем «Добавлено ✓»: если товар уже был в корзине,
      // это честнее, чем молчание
      btn.classList.add("added");
      btn.textContent = added ? "Добавлено ✓" : "Уже в корзине ✓";
      showToast(added ? "Схема добавлена в корзину" : "Эта схема уже в корзине");

      // Через 2 секунды возвращаем исходный текст кнопки
      setTimeout(function () {
        btn.classList.remove("added");
        btn.textContent = "Добавить в корзину";
      }, 2000);
    });
  });
});
