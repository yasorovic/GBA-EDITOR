-- Poursuite, patron 3 : la position de la cible n'est relue qu'une image sur quatre ; le mouvement a lieu à chaque image.
local cx = 0
local cy = 0

function on_update()
    if scene.frame % 4 == 0 then
        local cible = actor:get("Hero", 1)
        if cible then
            cx = cible.position.x
            cy = cible.position.y
        end
    end
    self:move_to(vec2(cx, cy), 1)
end
