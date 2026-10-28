// Pointe les boutons de téléchargement vers les fichiers de la dernière release GitHub.
// Les noms des fichiers contiennent la version : le lien direct ne peut donc pas être fixe.
// Sans réseau ou sans release, les boutons gardent leur lien vers la page des releases.
(function () {
  var API = "https://api.github.com/repos/victor3x0/GBA-EDITOR/releases/latest";
  var SUFFIXES = { windows: "-windows-setup.exe", linux: "-x86_64.AppImage.tar.gz" };

  function init() {
    var links = document.querySelectorAll("[data-download]");
    if (!links.length) return;
    fetch(API)
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (release) {
        if (!release || !release.assets) return;
        links.forEach(function (link) {
          var suffix = SUFFIXES[link.dataset.download];
          var asset = release.assets.find(function (a) { return a.name.endsWith(suffix); });
          if (asset) link.href = asset.browser_download_url;
        });
      })
      .catch(function () {});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
