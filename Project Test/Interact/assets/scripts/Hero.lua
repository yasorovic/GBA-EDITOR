-- Le joueur : la croix le déplace. Son regard (self.facing) suit son mouvement tout seul.
local speed = 1

function on_update()
    local dx = input:get_axis("horizontal")
    local dy = input:get_axis("vertical")
    self.velocity = vec2(dx * speed * 256, dy * speed * 256)
    self:apply_velocity()
end
