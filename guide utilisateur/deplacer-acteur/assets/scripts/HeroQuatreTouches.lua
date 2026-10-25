function on_start()
    self:play_anim("Idle")
end

function on_update()
    if input:held("left") then
        self.position = self.position + vec2(-1, 0)
    end
    if input:held("right") then
        self.position = self.position + vec2(1, 0)
    end
    if input:held("up") then
        self.position = self.position + vec2(0, -1)
    end
    if input:held("down") then
        self.position = self.position + vec2(0, 1)
    end
end
