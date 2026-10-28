-- Poursuite, patron 1 : on retrouve la cible à chaque image (actor:get) puis on avance vers elle (move_to).
function on_update()
    local cible = actor:get("Hero", 1)
    if cible then
        self:move_to(cible.position, 1)
    end
end
