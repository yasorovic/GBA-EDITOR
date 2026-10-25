exports = {
    vitesse    = { type = "int", default = 2,   label = "Vitesse",       min = 0, max = 8 },
    force_saut = { type = "int", default = 900, label = "Force du saut", min = 0, max = 2048 },
}

local gravite = 24

function on_start()
    self:play_anim("Idle")
end

function on_update()
    local vitesse_x = input:get_axis("horizontal") * vitesse * 256
    local vitesse_y = self.velocity.y + gravite

    if self.grounded and input:pressed("a") then
        vitesse_y = -force_saut
    end

    self.velocity = vec2(vitesse_x, vitesse_y)
    self:apply_velocity()
end
