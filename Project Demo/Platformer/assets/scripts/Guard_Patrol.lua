exports = {
    vitesse = { type = "int", default = 1, label = "Vitesse", min = 0, max = 4 },
    sens = { type = "int", default = 1, label = "Sens", min = -1, max = 1 },
}

function on_update()
    self.velocity = vec2(sens * vitesse * 256, 0)
    self:apply_velocity()
end

function on_tile_collide(normal_x, normal_y)
    if normal_x ~= 0 then
        sens = -sens
    end
end
