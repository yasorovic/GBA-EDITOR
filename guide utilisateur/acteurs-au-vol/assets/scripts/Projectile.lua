exports = {
    vitesse = { type = "int", default = 2, label = "Vitesse", min = 1, max = 8 },
}

function on_update()
    self.position = self.position + vec2(vitesse, 0)
    if self.position.x > scene.size.w then
        self:destroy()
    end
end
