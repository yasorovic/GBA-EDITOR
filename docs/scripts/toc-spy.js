/* « Sur cette page » : l'entrée sur laquelle on vient de cliquer reste celle qui est surlignée.
 *
 * Le suivi de lecture de Furo surligne la dernière rubrique dès que le bas de la page est atteint : cliquer sur
 * l'avant-dernière en surlignait une autre. Le clic fixe donc l'entrée, jusqu'au prochain geste de défilement
 * (molette, toucher, touches de navigation), qui rend la main au suivi. */
(function () {
  "use strict";

  var tree = document.querySelector(".toc-tree");
  if (!tree) { return; }

  var locked = null;
  var applying = false;

  function apply() {
    if (!locked) { return; }
    applying = true;
    tree.querySelectorAll("li").forEach(function (li) {
      li.classList.toggle("scroll-current", li === locked);
    });
    applying = false;
  }

  function release() {
    if (!locked) { return; }
    locked = null;
    window.dispatchEvent(new Event("scroll"));
  }

  tree.addEventListener("click", function (ev) {
    var link = ev.target.closest("a");
    if (!link) { return; }
    locked = link.closest("li");
    apply();
  });

  new MutationObserver(function () { if (!applying) { apply(); } })
    .observe(tree, { attributes: true, attributeFilter: ["class"], subtree: true });

  ["wheel", "touchmove"].forEach(function (name) {
    window.addEventListener(name, release, { passive: true });
  });
  window.addEventListener("keydown", function (ev) {
    if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].indexOf(ev.key) > -1) { release(); }
  });
})();
