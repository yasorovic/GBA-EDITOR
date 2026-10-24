function on_update()
    self:apply_velocity()
    local x = self.position.x
    local y = self.position.y
    if x < -8 or x > 240 or y < -8 or y > 160 then self:destroy() end
end
