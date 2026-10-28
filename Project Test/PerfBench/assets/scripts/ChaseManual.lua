-- Poursuite, patron 4 : pas de move_to, un pixel par axe vers la cible (math.sign), sans normaliser la direction.
function on_update()
    local cible = actor:get("Hero", 1)
    if cible then
        local dx = math.sign(cible.position.x - self.position.x)
        local dy = math.sign(cible.position.y - self.position.y)
        self.position = self.position + vec2(dx, dy)
    end
end
