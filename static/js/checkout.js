/* ==========================================================================
   checkout.js — страница оформления заказа (/checkout).

   Заполняет состав заказа из корзины (localStorage), подставляет id схем
   в скрытое поле формы и проверяет поля перед отправкой.
   Суммы сервер пересчитает сам — клиентским данным не доверяем.
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function () {

  const itemsBox = document.getElementById("checkout-items");
  if (!itemsBox) return; // мы не на странице оформления (например, показан успех)

  const idsField = document.getElementById("pattern-ids");
  const totalLine = document.getElementById("checkout-total-line");
  const totalEl = document.getElementById("checkout-total");
  const emptyNote = document.getElementById("checkout-empty-note");
  const form = document.getElementById("checkout-form");

  // --------------------------------------------------------------------------
  // Состав заказа из корзины
  // --------------------------------------------------------------------------
  const ids = getCart();                       // функция из cart.js
  const catalog = (function () {
    const el = document.getElementById("catalog-data");
    if (!el) return [];
    try { return JSON.parse(el.textContent); } catch (e) { return []; }
  })();

  const items = catalog.filter(function (p) { return ids.includes(p.id); });

  // Безопасное заполнение: textContent, не innerHTML
  itemsBox.textContent = "";
  items.forEach(function (p) {
    const li = document.createElement("li");

    const link = document.createElement("a");
    link.href = p.url;
    link.textContent = p.title;

    const price = document.createElement("span");
    price.textContent = p.price + " ₽";

    li.appendChild(link);
    li.appendChild(price);
    itemsBox.appendChild(li);
  });

  // Итоги и скрытое поле с id
  if (items.length > 0) {
    if (totalLine) totalLine.hidden = false;
    if (totalEl) totalEl.textContent = getCartTotal() + " ₽";
    if (emptyNote) emptyNote.hidden = true;
  }
  if (idsField) idsField.value = JSON.stringify(items.map(function (p) { return p.id; }));

  // --------------------------------------------------------------------------
  // Проверка полей формы перед отправкой (сервер тоже проверит — это двойная
  // защита, чтобы не мучить пользователя перезагрузкой при пустом поле)
  // --------------------------------------------------------------------------
  if (form) {
    form.addEventListener("submit", function (event) {
      let valid = true;

      const nameField = document.getElementById("field-name");
      const emailField = document.getElementById("field-email");

      // Убираем старые сообщения об ошибках
      form.querySelectorAll(".form-error:not(.form-error-general)").forEach(function (el) {
        el.remove();
      });
      [nameField, emailField].forEach(function (f) {
        if (f) f.removeAttribute("aria-invalid");
      });

      // Имя обязательно
      if (nameField && !nameField.value.trim()) {
        showFieldError(nameField, "Заполните это поле");
        valid = false;
      }

      // Почта: непустая и с "@" и точкой
      if (emailField) {
        const email = emailField.value.trim();
        const emailOk = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email);
        if (!email) {
          showFieldError(emailField, "Заполните это поле");
          valid = false;
        } else if (!emailOk) {
          showFieldError(emailField, "Проверьте адрес электронной почты");
          valid = false;
        }
      }

      if (!valid) {
        event.preventDefault(); // серверную проверку оставляем как страховку
      }
    });
  }

  /** Показывает сообщение об ошибке под полем и помечает поле. */
  function showFieldError(field, message) {
    field.setAttribute("aria-invalid", "true");
    const p = document.createElement("p");
    p.className = "form-error";
    p.setAttribute("role", "alert");
    p.textContent = message;
    field.insertAdjacentElement("afterend", p);
  }
});
