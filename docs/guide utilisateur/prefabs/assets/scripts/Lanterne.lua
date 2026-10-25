exports = {
    periode = { type = "int", default = 30, label = "Période", min = 2, max = 120 },
}

function on_update()
    if scene.frame % periode == 0 then
        if self.visible then
            self:hide()
        else
            self:show()
        end
    end
end
