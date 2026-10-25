exports = {
    vie_max = { type = "int", default = 20, label = "Vie maximale", min = 1, max = 999 },
}

local vie
local invincible = 0
local temps_degats = 0

function on_start()
    vie = vie_max
end

function subir_degats(degats)
    vie = math.max(0, vie - degats)
    if vie == 0 then
        self:destroy()
    end
end

function on_update()
    if input:pressed("b") then
        subir_degats(1)
    end

    if invincible > 0 then
        invincible = invincible - 1
        temps_degats = temps_degats + 1
        self:blink(temps_degats, 30, 3)
        self:shake(temps_degats, 8, 3)
    else
        temps_degats = 0
    end

    local remplissage = interface:get("Remplissage")
    local etat = vie * 4 / vie_max
    if etat == 0 then
        remplissage.state = "vie_0"
    elseif etat == 1 then
        remplissage.state = "vie_1"
    elseif etat == 2 then
        remplissage.state = "vie_2"
    elseif etat == 3 then
        remplissage.state = "vie_3"
    else
        remplissage.state = "vie_4"
    end
end

function on_collision_enter(other, my_box, other_box)
    if other.name == "Ennemi" and invincible == 0 then
        invincible = 30
        subir_degats(1)
    end
end
