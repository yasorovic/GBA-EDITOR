function on_update()
    if scene.frame % 90 == 0 then
        actor:spawn("Projectile", self.position)
    end
    if scene.frame % 90 == 45 then
        local p = actor:spawn("Projectile", self.position, { vitesse = 4 })
    end
end
