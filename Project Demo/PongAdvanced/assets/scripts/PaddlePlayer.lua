-- Raquette du joueur : haut / bas, bornée à l'écran (160 px - 32 px de raquette).
-- Au choc avec la balle, elle s'écrase en largeur (stretch) et part un peu de
-- travers (wobble). Les deux effets écrivent des canaux différents du sprite :
-- ils partagent le même compteur, et chacun retombe seul au neutre passé sa
-- durée, d'où l'appel à chaque frame, sans condition.
local hit_t = 99   -- au-delà des deux durées : aucun effet au démarrage

function on_update()
    local y = self.position.y

    if input:held("up") then
        y = y - 2
    end
    if input:held("down") then
        y = y + 2
    end

    self.position = vec2(self.position.x, math.clamp(y, 0, 128))

    if hit_t < 99 then
        hit_t = hit_t + 1
    end
    self:stretch(hit_t, 12, 30)
    self:wobble(hit_t, 18, 6)
end

function on_collision_enter(other, my_box, other_box)
    hit_t = 0
end
