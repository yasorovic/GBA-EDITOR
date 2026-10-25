-- Etats : 0 = attend, 1 = marche
local etat = 0
local minuteur = 0
local sens = 1

function on_start()
    etat = 0
    minuteur = 60
end

function on_update()
    if etat == 0 then
        self.velocity = vec2(0, 0)
        minuteur = minuteur - 1
        if minuteur <= 0 then
            etat = 1
        end
    elseif etat == 1 then
        self.velocity = vec2(sens * 256, 0)
    end
    self:apply_velocity()
end

function on_tile_collide(normal_x, normal_y)
    if normal_x ~= 0 and etat == 1 then
        sens = -sens
        etat = 0
        minuteur = 60
    end
end
