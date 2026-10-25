exports = {
    vitesse = { type = "int", default = 2, label = "Vitesse", min = 0, max = 8 },
}

function on_start()
    self:play_anim("Idle")
end

function on_update()
    self.position = self.position + input:get_axis("horizontal", "vertical") * vitesse
end
