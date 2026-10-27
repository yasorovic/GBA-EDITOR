-- Raquette du joueur : haut / bas, arrêtée par les murs de la carte de collision.
-- Au choc avec la balle, elle s'écrase en largeur (stretch) et part un peu de
-- travers (wobble). Les deux effets écrivent des canaux différents du sprite :
-- ils partagent le même compteur, et chacun retombe seul au neutre passé sa
-- durée, d'où l'appel à chaque frame, sans condition.
local hit_t = 99   -- au-delà des deux durées : aucun effet au démarrage

function on_update()
    local dy = 0

    if input:held("up") then
        dy = dy - 2
    end
    if input:held("down") then
        dy = dy + 2
    end

    -- Déplacement physique : la carte de collision arrête la raquette contre les
    -- murs haut et bas (self.position la téléporterait à travers).
    self.velocity = vec2(0, dy * 256)
    self:apply_velocity()

    if hit_t < 99 then
        hit_t = hit_t + 1
    end
    self:stretch(hit_t, 12, 30)
    self:wobble(hit_t, 18, 6)
end

function on_collision_enter(other, my_box, other_box)
    hit_t = 0
end
