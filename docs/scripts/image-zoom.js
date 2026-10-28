// Clic sur une capture de l'éditeur : elle s'ouvre en grand ; un clic ou Échap la referme.
(function () {
  "use strict";

  var overlay = null;

  function close() {
    if (!overlay) { return; }
    overlay.remove();
    overlay = null;
  }

  document.addEventListener("click", function (event) {
    var img = event.target.closest("img.backstage-screenshot");
    if (!img) { close(); return; }
    close();
    overlay = document.createElement("div");
    overlay.className = "backstage-zoom";
    var big = document.createElement("img");
    big.src = img.currentSrc || img.src;
    big.alt = img.alt;
    overlay.appendChild(big);
    document.body.appendChild(overlay);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") { close(); }
  });
})();
