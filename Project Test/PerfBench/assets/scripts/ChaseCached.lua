-- Poursuite, patron 2 : la référence est gardée d'une image à l'autre ; on ne la cherche que si elle est nulle.
local cible

function on_update()
    if cible == nil then
        cible = actor:get("Hero", 1)
    end
    if cible then
        self:move_to(cible.position, 1)
    end
end
