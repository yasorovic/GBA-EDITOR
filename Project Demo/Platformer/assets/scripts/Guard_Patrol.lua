exports = {
    speed = { type = "int", default = 1, label = "Vitesse", min = 0, max = 4 },
    dir = { type = "int", default = 1, label = "Sens", min = -1, max = 1 },
}

function on_update()
    self.velocity = vec2(dir * speed * 256, 0)
    self:apply_velocity()
end

function on_tile_collide(normal_x, normal_y) -- check if there is a wall
    if normal_x ~= 0 then
        dir = -dir -- change direction automaticaly when meeting a wall
    end
end
