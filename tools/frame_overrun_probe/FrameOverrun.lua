-- FrameOverrun.lua — sonde : que devient le jeu quand le travail d'une image dure
-- PLUS qu'une image ?
--
-- À attacher à un acteur visible (un sprite quelconque) d'une scène de test.
-- Chaque tour de boucle, le script brûle de plus en plus de temps : un palier
-- de charge toutes les `ramp_every` images, jusqu'à `work_max`. On regarde alors,
-- côté émulateur (mgba_frame_probe.lua), combien de tours de boucle passent par
-- rafraîchissement d'écran. Le protocole est dans README.md.
--
-- L'acteur se déplace d'un côté à l'autre : le résultat du calcul sert de
-- position, ce qui empêche le compilateur de supprimer la boucle (une valeur que
-- personne ne lit est un calcul qu'il retire).

exports = {
    ramp_every = { type = "int", default = 20,    label = "Images par palier", min = 1, max = 600 },
    ramp_step  = { type = "int", default = 150,   label = "Charge par palier",  min = 1, max = 5000 },
    work_max   = { type = "int", default = 12000, label = "Charge maximale",    min = 0, max = 60000 },
}

local acc = 0

function on_update()
    -- Palier courant : `scene.frame` compte les tours de boucle du moteur.
    local work = (scene.frame / ramp_every) * ramp_step
    if work > work_max then work = work_max end

    -- Charge pure : un modulo à chaque tour (la division est logicielle sur
    -- ARM7TDMI, donc coûteuse et sans forme close que le compilateur pourrait
    -- calculer d'un coup).
    for i = 1, work do
        acc = (acc * 3 + i) % 1021
    end

    self.position = vec2(20 + acc % 200, 80)
end
