-- Avance d'un pixel par image : sa position prouve que son on_update tourne.
function on_update()
    self.velocity = vec2(256, 0)
    self:apply_velocity()
end
