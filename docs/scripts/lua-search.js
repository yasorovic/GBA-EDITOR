/* Auto-complétion des fonctions de l'API dans le champ de recherche du menu.
 *
 * L'index (`_static/lua-api-index.json`) est généré avec le catalogue par docs/_gen/lua_api.py : une entrée par
 * fonction et par groupe. Rien n'est chargé avant le premier clic dans le champ. Sans résultat sélectionné,
 * Entrée lance la recherche habituelle de Sphinx. Le raccourci « / » donne le focus au champ. */
(function () {
  "use strict";

  var MAX_RESULTS = 8;
  var input = document.querySelector(".sidebar-search");
  if (!input) { return; }

  var root = document.documentElement.dataset.content_root || "";
  var index = null;
  var loading = null;
  var results = [];
  var selected = -1;

  var list = document.createElement("ul");
  list.className = "lua-search-results";
  list.hidden = true;
  list.setAttribute("role", "listbox");
  input.closest("form").appendChild(list);

  function load() {
    if (!loading) {
      loading = fetch(root + "_static/lua-api-index.json")
        .then(function (r) { return r.ok ? r.json() : []; })
        .catch(function () { return []; })
        .then(function (data) {
          index = data.map(function (e) {
            var name = e.n.toLowerCase();
            return { e: e, name: name, bare: name.split(/[:.]/).pop(), desc: e.d.toLowerCase(), group: e.g.toLowerCase() };
          });
          return index;
        });
    }
    return loading;
  }

  function score(item, q) {
    if (item.bare === q) { return 100; }
    if (item.bare.indexOf(q) === 0) { return 80; }
    if (item.name.indexOf(q) === 0) { return 70; }
    if (item.bare.indexOf(q) > -1) { return 50; }
    if (item.name.indexOf(q) > -1) { return 40; }
    if (item.group.indexOf(q) > -1) { return 30; }
    if (item.desc.indexOf(q) > -1) { return 20; }
    return 0;
  }

  function search(query) {
    var q = query.trim().toLowerCase();
    if (!q || !index) { return []; }
    return index
      .map(function (item) { return { item: item, score: score(item, q) }; })
      .filter(function (r) { return r.score > 0; })
      .sort(function (a, b) { return b.score - a.score || a.item.name.localeCompare(b.item.name); })
      .slice(0, MAX_RESULTS)
      .map(function (r) { return r.item.e; });
  }

  function render() {
    list.textContent = "";
    results.forEach(function (e, i) {
      var li = document.createElement("li");
      li.setAttribute("role", "option");
      var a = document.createElement("a");
      a.href = root + e.u;
      var name = document.createElement("span");
      name.className = "lua-search-name";
      name.textContent = e.t === "group" ? e.n : e.s;
      var group = document.createElement("span");
      group.className = "lua-search-group";
      group.textContent = e.t === "group" ? "Groupe" : e.g;
      var desc = document.createElement("span");
      desc.className = "lua-search-desc";
      desc.textContent = e.d;
      a.append(name, group, desc);
      li.appendChild(a);
      if (i === selected) { li.className = "selected"; }
      list.appendChild(li);
    });
    list.hidden = results.length === 0;
  }

  function update() {
    load().then(function () {
      results = search(input.value);
      selected = -1;
      render();
    });
  }

  function close() {
    list.hidden = true;
    selected = -1;
  }

  input.addEventListener("focus", load);
  input.addEventListener("input", update);
  input.addEventListener("blur", function () { setTimeout(close, 150); });

  input.addEventListener("keydown", function (ev) {
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      if (!results.length) { return; }
      ev.preventDefault();
      var step = ev.key === "ArrowDown" ? 1 : -1;
      selected = (selected + step + results.length + 1) % (results.length + 1);
      if (selected === results.length) { selected = -1; }
      render();
    } else if (ev.key === "Enter" && selected > -1) {
      ev.preventDefault();
      window.location.href = root + results[selected].u;
    } else if (ev.key === "Escape") {
      close();
    }
  });

  document.addEventListener("keydown", function (ev) {
    var t = ev.target;
    var typing = t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
    if (ev.key === "/" && !typing && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
      ev.preventDefault();
      input.focus();
    }
  });
})();
