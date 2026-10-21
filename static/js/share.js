/* ==========================================================================
   share.js — кнопка «Поделиться» для схем.

   Как это работает:
   1) Если браузер умеет системное окно «Поделиться» (navigator.share),
      открываем его — там человек сам выберет приложение.
   2) Если не умеет — открываем небольшое меню со ссылками:
        * «Скопировать ссылку»
        * Telegram
        * WhatsApp
        * ВКонтакте

   ВАЖНО: кнопка делится ТОЛЬКО публичной страницей схемы.
   Ссылки на платные файлы (PDF и т. п.) никогда не передаются —
   они и так недоступны без права скачивания.

   Разметка кнопки:
     <button class="share-button"
             data-share-url="https://адрес/pattern/... "
             data-share-title="Название схемы"
             data-share-text="Короткий текст-приглашение">Поделиться</button>
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function () {

  // --- Небольшое меню появляется рядом с кнопкой ---
  let openMenu = null;

  function closeMenu() {
    if (openMenu) {
      openMenu.remove();
      openMenu = null;
    }
  }

  // Закрытие меню: клик мимо, Escape, прокрутка
  document.addEventListener("click", function (event) {
    if (openMenu && !openMenu.contains(event.target) &&
        !event.target.closest(".share-button")) {
      closeMenu();
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeMenu();
  });
  window.addEventListener("scroll", closeMenu, { passive: true });

  /** Показывает меню запасных вариантов под кнопкой. */
  function showFallbackMenu(button, url, title, text) {
    closeMenu();

    const menu = document.createElement("div");
    menu.className = "share-menu";
    menu.setAttribute("role", "menu");

    const encodedUrl = encodeURIComponent(url);
    const encodedText = encodeURIComponent(text + " " + url);

    // 1. Копировать ссылку — работает всегда
    const copyButton = document.createElement("button");
    copyButton.type = "button";
    copyButton.className = "share-menu-item";
    copyButton.setAttribute("role", "menuitem");
    copyButton.textContent = "Скопировать ссылку";
    copyButton.addEventListener("click", function () {
      copyToClipboard(url, button);
      closeMenu();
    });
    menu.appendChild(copyButton);

    // 2. Telegram — официальная схема ссылки t.me/share/url
    const telegram = document.createElement("a");
    telegram.className = "share-menu-item";
    telegram.setAttribute("role", "menuitem");
    telegram.href = "https://t.me/share/url?url=" + encodedUrl +
                     "&text=" + encodeURIComponent(text);
    telegram.target = "_blank";
    telegram.rel = "noopener";
    telegram.textContent = "Telegram";
    menu.appendChild(telegram);

    // 3. WhatsApp — официальная схема wa.me/?text=
    const whatsapp = document.createElement("a");
    whatsapp.className = "share-menu-item";
    whatsapp.setAttribute("role", "menuitem");
    whatsapp.href = "https://wa.me/?text=" + encodedText;
    whatsapp.target = "_blank";
    whatsapp.rel = "noopener";
    whatsapp.textContent = "WhatsApp";
    menu.appendChild(whatsapp);

    // 4. ВКонтакте — официальная схема vk.com/share.php
    const vk = document.createElement("a");
    vk.className = "share-menu-item";
    vk.setAttribute("role", "menuitem");
    vk.href = "https://vk.com/share.php?url=" + encodedUrl + "&title=" +
              encodeURIComponent(title);
    vk.target = "_blank";
    vk.rel = "noopener";
    vk.textContent = "ВКонтакте";
    menu.appendChild(vk);

    // Ставим меню под кнопкой
    const holder = button.closest(".share-holder") || button.parentElement;
    holder.style.position = "relative";
    holder.appendChild(menu);
    openMenu = menu;
  }

  /** Копирует ссылку в буфер обмена и показывает сообщение. */
  function copyToClipboard(url, button) {
    function done() {
      showToast("Ссылка скопирована");
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done).catch(function () {
        fallbackCopy(url, done);
      });
    } else {
      fallbackCopy(url, done);
    }
  }

  /** Старый способ копирования — если браузер не даёт доступ к буферу. */
  function fallbackCopy(url, done) {
    const field = document.createElement("textarea");
    field.value = url;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    try {
      document.execCommand("copy");
      done();
    } catch (error) {
      // Честно говорим, что автоматически скопировать не получилось
      showToast("Не удалось скопировать. Ссылка: " + url, true);
    }
    document.body.removeChild(field);
  }

  /** Показывает всплывающее уведомление (используется и корзиной). */
  function showToast(message, long) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("is-visible");
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(function () {
      toast.classList.remove("is-visible");
    }, long ? 6000 : 2200);
  }

  // --- Обработчик всех кнопок «Поделиться» на странице ---
  document.querySelectorAll(".share-button").forEach(function (button) {
    button.addEventListener("click", function () {
      const url = button.dataset.shareUrl || window.location.href;
      const title = button.dataset.shareTitle || document.title;
      const text = button.dataset.shareText || "Посмотрите эту схему вышивки";

      // Системное окно «Поделиться» — если браузер поддерживает
      if (navigator.share) {
        navigator.share({ title: title, text: text, url: url }).catch(function (error) {
          // Пользователь мог просто закрыть окно — это не ошибка
          if (error && error.name !== "AbortError") {
            showFallbackMenu(button, url, title, text);
          }
        });
      } else {
        showFallbackMenu(button, url, title, text);
      }
    });
  });
});
