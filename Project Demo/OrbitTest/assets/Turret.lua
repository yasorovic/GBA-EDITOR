exports = {
    turn_speed = { type = "int", default = 2, label = "Rotation (deg par frame)", min = 0, max = 20 },
    fire_interval = { type = "int", default = 30, label = "Intervalle de tir (frames)", min = 1, max = 240 },
    bullet_speed = { type = "int", default = 2, label = "Vitesse du projectile", min = 1, max = 8 },
}

local aim = 0
local timer = 0

-- Le sprite tourne autour de son centre (sprite_rotation) ; la position de la tourelle
-- est ce centre, et 0 degre pointe vers la droite, comme math.atan2.
function on_update()
    aim = (aim + turn_speed) % 360
    self.sprite_rotation = aim
    timer = timer + 1
    if timer >= fire_interval then
        timer = 0
        local x = self.position.x + 10 * math.cos(aim) / 256 - 4
        local y = self.position.y + 10 * math.sin(aim) / 256 - 4
        local shot = actor:spawn("Bullet", vec2(x, y))
        if shot ~= nil then
            shot.velocity = vec2(bullet_speed * math.cos(aim), bullet_speed * math.sin(aim))
        end
    end
end
