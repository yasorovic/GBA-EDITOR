local vitesse = 2

function on_start()
    self:play_anim("Idle")
end

function on_update()
    self.velocity = input:get_axis("horizontal", "vertical") * vitesse * 256
    self:apply_velocity()
end
