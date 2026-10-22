"use strict";
const current = document.body.dataset.page;
const activeLink = document.querySelector(`[data-nav="${current}"]`);
if (activeLink) {
  activeLink.classList.add("active");
  activeLink.setAttribute("aria-current", "page");
}
